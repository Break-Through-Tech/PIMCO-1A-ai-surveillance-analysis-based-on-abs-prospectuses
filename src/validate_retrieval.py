"""Prove retrieval is sound before anyone trusts an answer it produces.

The quiet failure here is different from the chunking one. Chunks could silently
drop text; retrieval can silently drop DEALS, because one passage stands in for
every deal that contains it. If that expansion is wrong, an answer names three
deals when it should name thirty and nothing looks broken.

Check A is the one that guards that. The rest cover filtering, citations,
question coverage and whether results are just the same passage repeated.

Usage:
    python src/validate_retrieval.py
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from embed import DEFAULT_BACKEND, load_passages
from semantic_search import load_deals, matching_accessions, search

DATA = Path("data")
QUESTIONS = DATA / "test_questions.txt"
SPACES = re.compile(r"\s+")


def load_questions():
    return [l.strip() for l in QUESTIONS.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def check(name, failures, detail=""):
    status = "PASS" if not failures else "FAIL"
    print(f"[{status}] {name}: {len(failures)} problem(s){detail}")
    for item in failures[:4]:
        print(f"        {item}")
    return not failures


def main():
    backend = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BACKEND
    deals = load_deals()
    questions = load_questions()
    results = []

    # A. Expanding a passage back to deals must not lose or invent any.
    _, _, where = load_passages()
    bad = []
    for question in questions[:6]:
        for hit in search(question, backend=backend, top_k=5):
            got = {d["deal_name"] for d in hit["deals"]}
            sha = next(s for s, recs in where.items()
                       if recs[0]["text"] == hit["text"])
            want_acc = {r["accession"] for r in where[sha]
                        if r["section_kind"] in ("body", "glossary")}
            want = set(deals[deals.accession.isin(want_acc)].deal_name)
            if got != want:
                bad.append(f"{len(got)} deals returned, {len(want)} carry the passage")
    results.append(check("A passage expands to every deal that has it", bad))

    # B. The metadata filter has to narrow, not decorate.
    bad = []
    q = "where are collections initially deposited?"
    wide = search(q, backend=backend, top_k=20)
    narrow = search(q, backend=backend, issuer="Toyota", top_k=20)
    allowed = matching_accessions(deals, issuer="Toyota")
    names = set(deals[deals.accession.isin(allowed)].deal_name)
    for hit in narrow:
        stray = [d["deal_name"] for d in hit["deals"] if d["deal_name"] not in names]
        if stray:
            bad.append(f"filter leaked: {stray[:2]}")
    if len(allowed) >= len(deals):
        bad.append("issuer filter matched every deal")
    results.append(check("B metadata filter narrows the corpus", bad,
                         f", {len(deals)} deals -> {len(allowed)} for Toyota"))

    # C. A citation that does not resolve is worse than no citation.
    bad = []
    for question in questions[:8]:
        for hit in search(question, backend=backend, top_k=3):
            cite = hit["deals"][0]
            source = Path(cite["text_file"]).read_text(encoding="utf-8")
            span = SPACES.sub(" ", source[cite["char_start"]:cite["char_end"]])
            probe = SPACES.sub(" ", hit["text"].split("\n")[0]).strip()[:60]
            if probe and probe not in span:
                bad.append(f"{cite['deal_name'][:40]} p{cite['page']}: span mismatch")
    results.append(check("C citations resolve to the source text", bad))

    # D. Coverage, not quality. A question returning nothing is either a bug or
    # a real gap in the corpus, and we need to know which before the check-in.
    bad = []
    for question in questions:
        if not search(question, backend=backend, top_k=5):
            bad.append(f"no results: {question[:62]}")
    results.append(check("D every test question returns something", bad,
                         f", {len(questions)} questions"))

    # E. The vocabulary gap. "eVault" appears in zero of 129 documents but the
    # concept appears as "electronic contract" in 78%. This is the clearest
    # single reason Milestone 2 exists.
    hits = search("Are the documents custodied using third-party software (eVault)?",
                  backend=backend, top_k=10)
    blob = " ".join(h["text"] for h in hits).casefold()
    found = [t for t in ("electronic contract", "electronic chattel paper",
                         "custodian", "eVault".casefold()) if t in blob]
    bad = [] if any(t in blob for t in ("electronic contract", "electronic chattel paper")) \
        else ["eVault query surfaced no electronic-contract language"]
    results.append(check("E eVault question reaches electronic-contract text", bad,
                         f", matched {found}"))

    # F. Before dedup, a commingling query returned a top 10 holding 2 distinct
    # passages, one of them filling 9 slots.
    bad = []
    for question in ("commingling of collections by the servicer",
                     "where are collections initially deposited?"):
        hits = search(question, backend=backend, top_k=10)
        texts = {h["text"] for h in hits}
        if len(texts) != len(hits):
            bad.append(f"{len(hits) - len(texts)} duplicate passages in top 10")
    results.append(check("F top results are distinct passages", bad))

    print("\n" + "=" * 70)
    passed = sum(results)
    print(f"RETRIEVAL VALIDATION ({backend}): {passed}/{len(results)} checks passed")


if __name__ == "__main__":
    main()
