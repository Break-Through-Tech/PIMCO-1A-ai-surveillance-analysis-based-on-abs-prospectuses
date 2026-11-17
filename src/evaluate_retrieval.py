"""Evaluate semantic retrieval against a small, human-verified question set.

The retrieval backend is supplied by Milestone 2 Task 3. It must expose a
function accepting ``query`` and ``top_k`` and return ranked records containing
non-empty ``text`` and either an ``accession`` or a ``deals`` list containing
accessions. Shared passages count as one rank, even when they cite many deals.

Usage:
    python src/evaluate_retrieval.py --retriever semantic_search:search
"""

import argparse
import csv
from functools import partial
import importlib
import json
import re
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUESTIONS = ROOT / "data" / "evaluation_questions.jsonl"
DEFAULT_DEALS = ROOT / "data" / "deal_index.csv"
DEFAULT_CHUNK_INDEX = ROOT / "data" / "chunk_index.csv"
DEFAULT_CHUNKS = ROOT / "data" / "chunks"
DEFAULT_REPORT = ROOT / "data" / "retrieval_evaluation.csv"
SPACE = re.compile(r"\s+")


def load_questions(path):
    """Load and check one evaluation case per JSONL line."""
    questions = []
    seen_ids = set()

    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            try:
                question = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {exc.msg}"
                ) from exc

            if not isinstance(question, dict):
                raise ValueError(f"{path}:{line_number}: each JSONL record must be an object")
            required = {"question_id", "question", "expected_deal_ids",
                        "supporting_passages"}
            missing = required - question.keys()
            if missing:
                raise ValueError(
                    f"{path}:{line_number}: missing fields: "
                    f"{', '.join(sorted(missing))}"
                )

            question_id = question["question_id"]
            if not isinstance(question_id, str) or not question_id.strip():
                raise ValueError(f"{path}:{line_number}: question_id must be non-empty")
            if question_id in seen_ids:
                raise ValueError(f"{path}:{line_number}: duplicate question_id {question_id!r}")
            seen_ids.add(question_id)

            if not isinstance(question["question"], str) or not question["question"].strip():
                raise ValueError(f"{path}:{line_number}: question must be non-empty")

            expected = question["expected_deal_ids"]
            if (not isinstance(expected, list) or not expected
                    or any(not isinstance(item, str) or not item for item in expected)):
                raise ValueError(
                    f"{path}:{line_number}: expected_deal_ids must be a non-empty list of accessions"
                )

            passages = question["supporting_passages"]
            if (not isinstance(passages, list) or not passages
                    or any(not isinstance(item, dict)
                           or not isinstance(item.get("accession"), str)
                           or not item["accession"]
                           or not isinstance(item.get("quote"), str)
                           or not item["quote"].strip()
                           for item in passages)):
                raise ValueError(
                    f"{path}:{line_number}: each supporting passage needs an accession and quote"
                )
            supported = {item["accession"] for item in passages}
            if not set(expected).issubset(supported):
                raise ValueError(
                    f"{path}:{line_number}: every expected deal needs a supporting passage"
                )
            questions.append(question)

    if not questions:
        raise ValueError(f"No evaluation questions found in {path}")
    return questions


def validate_supporting_passages(questions, chunk_index_path, chunks_dir):
    """Ensure every gold quote occurs in a stored chunk for its deal."""
    chunk_index = pd.read_csv(chunk_index_path, dtype=str).fillna("")
    required_columns = {"accession", "chunk_file"}
    missing_columns = required_columns - set(chunk_index.columns)
    if missing_columns:
        raise ValueError(
            f"{chunk_index_path} is missing columns: {', '.join(sorted(missing_columns))}"
        )
    files_by_accession = {}
    for row in chunk_index.itertuples(index=False):
        files_by_accession.setdefault(row.accession, []).append(row.chunk_file)

    for question in questions:
        for evidence in question["supporting_passages"]:
            accession = evidence["accession"]
            chunk_files = files_by_accession.get(accession, [])
            if not chunk_files:
                raise ValueError(
                    f"{question['question_id']}: no chunk-index entry for evidence "
                    f"accession {accession}"
                )

            quote = SPACE.sub(" ", evidence["quote"]).strip().casefold()
            found = False
            for relative_path in chunk_files:
                indexed_path = Path(relative_path)
                chunk_path = (
                    indexed_path if indexed_path.is_absolute()
                    else Path(chunks_dir) / indexed_path.name
                )
                if not chunk_path.exists():
                    chunk_path = ROOT / indexed_path
                if not chunk_path.exists():
                    raise FileNotFoundError(
                        f"Missing chunk file {chunk_path}; run python src/run_chunk.py first."
                    )
                with chunk_path.open(encoding="utf-8") as stream:
                    for line_number, line in enumerate(stream, start=1):
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ValueError(
                                f"{chunk_path}:{line_number}: invalid chunk JSON"
                            ) from exc
                        if (chunk.get("accession") == accession
                                and quote in SPACE.sub(" ", chunk.get("text", "")).strip().casefold()):
                            found = True
                            break
                if found:
                    break
            if not found:
                raise ValueError(
                    f"{question['question_id']}: supporting quote is not present in a "
                    f"chunk for accession {accession}"
                )


def _result_records(results):
    if isinstance(results, pd.DataFrame):
        records = results.to_dict(orient="records")
    else:
        records = list(results)
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("Retriever results must be passage records")
        if "deals" in record:
            if (not isinstance(record["deals"], list) or not record["deals"]
                    or any(not isinstance(d, Mapping) or not d.get("accession")
                           for d in record["deals"])):
                raise ValueError("Grouped results need non-empty deals with accessions")
        elif not record.get("accession"):
            raise ValueError("Retriever results must be records with a non-empty accession")
    return records


def normalize_evidence(text):
    """Ignore capitalization and whitespace, preserving words and punctuation."""
    return SPACE.sub(" ", text).strip().casefold()


def evaluate_questions(questions: Sequence[dict], retriever: Callable,
                       deals: pd.DataFrame, top_k=5):
    """Score only the first top_k passages, before deduplicating deal IDs.

    Evidence success requires one annotated quote per expected deal, in a
    passage from that same deal. Unannotated paraphrases need human review.
    """
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if not questions:
        raise ValueError("No evaluation questions supplied")
    deal_names = deals.set_index("accession")["deal_name"].to_dict()
    report = []
    for question in questions:
        expected = list(dict.fromkeys(question["expected_deal_ids"]))
        for accession in expected:
            if accession not in deal_names:
                raise ValueError(f"Expected accession {accession!r} absent from deal_index.csv")
        results = _result_records(retriever(question["question"], top_k=top_k))[:top_k]
        ranked_accessions, diagnostics = [], []
        deal_ranks, evidence_ranks = {}, {}
        for rank, result in enumerate(results, 1):
            # A shared passage still occupies one result slot, regardless of
            # how many filings contain it. Never flatten before top-five scoring.
            citations = result.get("deals", [{"accession": result.get("accession")}])
            accessions = list(dict.fromkeys(str(d["accession"]) for d in citations))
            text = result.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Retriever results need non-empty text to check supporting passages")
            matched_accessions = []
            for accession in accessions:
                if accession not in deal_names:
                    raise ValueError(f"Retriever returned accession {accession!r} absent from deal_index.csv")
                if accession not in deal_ranks:
                    ranked_accessions.append(accession)
                    deal_ranks[accession] = rank
                matched = accession in expected and any(
                    evidence["accession"] == accession
                    and normalize_evidence(evidence["quote"]) in normalize_evidence(text)
                    for evidence in question["supporting_passages"]
                )
                if matched:
                    evidence_ranks.setdefault(accession, rank)
                    matched_accessions.append(accession)
            diagnostics.append({"rank": rank, "accessions": accessions,
                "chunk_id": result.get("chunk_id", ""), "text": text,
                "score": result.get("score"), "deals": citations,
                "supporting_quote_matched": bool(matched_accessions),
                "matched_expected_deal_ids": matched_accessions})
        found = [a for a in expected if a in deal_ranks]
        missing = [a for a in expected if a not in deal_ranks]
        supported = [a for a in expected if a in evidence_ranks]
        unsupported = [a for a in expected if a not in evidence_ranks]
        report.append({
            "question_id": question["question_id"], "question": question["question"],
            "expected_deal_ids": "|".join(expected),
            "retrieved_deal_ids": "|".join(ranked_accessions),
            "retrieved_deal_names": "|".join(deal_names[a] for a in ranked_accessions),
            "found_expected_deal_ids": "|".join(found),
            "missing_expected_deal_ids": "|".join(missing), "top_k": top_k,
            "recall_at_k": len(found) / len(expected),
            "reciprocal_rank": 1 / min(deal_ranks[a] for a in found) if found else 0.0,
            "deal_passed_at_k": not missing,
            "supported_deal_ids": "|".join(supported),
            "missing_supporting_deal_ids": "|".join(unsupported),
            "passage_recall_at_k": len(supported) / len(expected),
            "passage_reciprocal_rank": 1 / min(evidence_ranks.values()) if evidence_ranks else 0.0,
            "passage_passed_at_k": not unsupported,
            "passed_at_k": not unsupported,
            "failure_reason": ("expected_deal_missing" if missing else
                               "supporting_quote_not_found" if unsupported else ""),
            "retrieved_passages": json.dumps(diagnostics, ensure_ascii=False),
        })
    return report


def load_retriever(spec):
    """Import a retrieval function as ``module:function``."""
    module_name, separator, function_name = spec.partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("--retriever must use module:function format")
    module = importlib.import_module(module_name)
    retriever = getattr(module, function_name)
    if not callable(retriever):
        raise TypeError(f"{spec} is not callable")
    return retriever


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retriever",
        default="semantic_search:search",
        help="Task 3 search function in module:function form",
    )
    parser.add_argument("--backend", choices=("openai", "tfidf"), default="openai",
                        help="Search backend; tfidf is a local lexical baseline")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--deals", type=Path, default=DEFAULT_DEALS)
    parser.add_argument("--chunk-index", type=Path, default=DEFAULT_CHUNK_INDEX)
    parser.add_argument("--chunks-dir", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    questions = load_questions(args.questions)
    validate_supporting_passages(questions, args.chunk_index, args.chunks_dir)
    deals = pd.read_csv(args.deals, dtype=str).fillna("")
    retriever = load_retriever(args.retriever)
    if args.retriever in ("semantic_search:search", "src.semantic_search:search"):
        retriever = partial(retriever, backend=args.backend)
    report = evaluate_questions(
        questions, retriever, deals, top_k=args.top_k
    )

    for row in report:
        row["retriever"] = args.retriever
        row["backend"] = args.backend if args.retriever in (
            "semantic_search:search", "src.semantic_search:search") else "custom"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=report[0].keys())
        writer.writeheader()
        writer.writerows(report)

    passed = sum(row["passed_at_k"] for row in report)
    deal_passed = sum(row["deal_passed_at_k"] for row in report)
    mean_recall = sum(row["recall_at_k"] for row in report) / len(report)
    mean_rr = sum(row["reciprocal_rank"] for row in report) / len(report)
    print(f"Correct deals within first {args.top_k} passages: {deal_passed}/{len(report)}")
    print(f"Supporting quotes within first {args.top_k} passages: {passed}/{len(report)}")
    print(f"Mean recall@{args.top_k}: {mean_recall:.3f}")
    print(f"Mean reciprocal rank: {mean_rr:.3f}")
    print(f"Evaluation report: {args.output}")
    for row in report:
        if not row["passed_at_k"]:
            print(
                f"FAIL {row['question_id']}: expected "
                f"{row['missing_expected_deal_ids']}; missing evidence for "
                f"{row['missing_supporting_deal_ids']}; got {row['retrieved_deal_ids']}"
            )


if __name__ == "__main__":
    main()
