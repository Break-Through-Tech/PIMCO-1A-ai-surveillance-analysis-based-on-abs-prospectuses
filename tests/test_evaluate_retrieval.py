import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.evaluate_retrieval import (
    evaluate_questions,
    load_questions,
    validate_supporting_passages,
)


class EvaluateRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.deals = pd.DataFrame([
            {"accession": "a", "deal_name": "Deal A"},
            {"accession": "b", "deal_name": "Deal B"},
            {"accession": "c", "deal_name": "Deal C"},
        ])
        self.question = {
            "question_id": "q1",
            "question": "Which deal?",
            "expected_deal_ids": ["b", "c"],
            "supporting_passages": [
                {"accession": "b", "quote": "Evidence B"},
                {"accession": "c", "quote": "Evidence C"},
            ],
        }

    def test_preserves_passage_ranks_with_repeated_deals(self):
        def retrieve(query, top_k):
            return [
                {"accession": "a", "chunk_id": "a1", "text": "Other"},
                {"accession": "a", "chunk_id": "a2", "text": "Other"},
                {"accession": "b", "chunk_id": "b1", "text": "Evidence B"},
                {"accession": "c", "chunk_id": "c1", "text": "Evidence C"},
            ]

        row = evaluate_questions([self.question], retrieve, self.deals)[0]

        self.assertEqual(row["retrieved_deal_ids"], "a|b|c")
        self.assertEqual(row["recall_at_k"], 1.0)
        self.assertEqual(row["reciprocal_rank"], 1 / 3)
        self.assertTrue(row["passed_at_k"])

    def test_records_expected_deals_missing_from_top_five(self):
        def retrieve(query, top_k):
            return [{"accession": "a", "text": "Other"}]

        row = evaluate_questions(
            [self.question], retrieve, self.deals, top_k=1
        )[0]

        self.assertEqual(row["missing_expected_deal_ids"], "b|c")
        self.assertEqual(row["recall_at_k"], 0.0)
        self.assertFalse(row["passed_at_k"])

    def test_rejects_accession_not_in_deal_index(self):
        def retrieve(query, top_k):
            return [{"accession": "unknown"}]

        with self.assertRaisesRegex(ValueError, "absent from deal_index"):
            evaluate_questions([self.question], retrieve, self.deals)

    def single_deal_question(self):
        return {**self.question, "expected_deal_ids": ["b"],
                "supporting_passages": [{"accession": "b", "quote": "Evidence B"}]}

    def test_supporting_quote_at_rank_five_passes(self):
        def retrieve(query, top_k):
            self.assertEqual(top_k, 5)
            self.assertEqual(query, self.question["question"])
            return ([{"accession": "a", "text": "Other"}] * 4
                    + [{"accession": "b", "text": "More EVIDENCE\n  B here."}])
        row = evaluate_questions([self.single_deal_question()], retrieve, self.deals)[0]
        self.assertTrue(row["passed_at_k"])
        self.assertEqual(row["passage_reciprocal_rank"], 0.2)

    def test_supporting_quote_only_at_rank_six_fails(self):
        def retrieve(query, top_k):
            return ([{"accession": "a", "text": "Other"}] * 5
                    + [{"accession": "b", "text": "Evidence B"}])
        row = evaluate_questions([self.single_deal_question()], retrieve, self.deals)[0]
        self.assertFalse(row["deal_passed_at_k"])
        self.assertFalse(row["passed_at_k"])
        self.assertEqual(len(json.loads(row["retrieved_passages"])), 5)

    def test_correct_deal_wrong_passage_fails(self):
        row = evaluate_questions([self.single_deal_question()],
            lambda query, top_k: [{"accession": "b", "text": "Interest rates"}], self.deals)[0]
        self.assertTrue(row["deal_passed_at_k"])
        self.assertFalse(row["passage_passed_at_k"])
        self.assertEqual(row["failure_reason"], "supporting_quote_not_found")

    def test_quote_from_wrong_deal_does_not_count(self):
        row = evaluate_questions([self.single_deal_question()],
            lambda query, top_k: [{"accession": "a", "text": "Evidence B"}], self.deals)[0]
        self.assertFalse(row["passed_at_k"])

    def test_empty_results_fail(self):
        row = evaluate_questions([self.question], lambda query, top_k: [], self.deals)[0]
        self.assertFalse(row["passed_at_k"])
        self.assertEqual(row["passage_recall_at_k"], 0)

    def test_missing_text_is_an_interface_error(self):
        with self.assertRaisesRegex(ValueError, "non-empty text"):
            evaluate_questions([self.question],
                lambda query, top_k: [{"accession": "b"}], self.deals)

    def test_alternative_annotated_quote_counts(self):
        question = self.single_deal_question()
        question["supporting_passages"].append({"accession": "b", "quote": "Alternative proof"})
        row = evaluate_questions([question], lambda query, top_k:
            [{"accession": "b", "text": "Alternative proof"}], self.deals)[0]
        self.assertTrue(row["passed_at_k"])

    def test_all_expected_deals_need_evidence(self):
        row = evaluate_questions([self.question], lambda query, top_k:
            [{"accession": "b", "text": "Evidence B"},
             {"accession": "c", "text": "Unrelated"}], self.deals)[0]
        self.assertTrue(row["deal_passed_at_k"])
        self.assertFalse(row["passed_at_k"])
        self.assertEqual(row["passage_recall_at_k"], 0.5)
        self.assertEqual(row["missing_supporting_deal_ids"], "c")

    def test_requires_supporting_passage_for_each_expected_deal(self):
        question = dict(self.question)
        question["supporting_passages"] = [{"accession": "b", "quote": "Evidence B"}]

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.jsonl"
            path.write_text(json.dumps(question) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "every expected deal"):
                load_questions(path)

    def test_loads_questions_with_header_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.jsonl"
            path.write_text(
                "# These questions test retrieval.\n\n"
                + json.dumps(self.question) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(load_questions(path), [self.question])

    def test_checks_gold_quote_against_stored_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chunks = root / "chunks"
            chunks.mkdir()
            chunk_file = chunks / "sample.jsonl"
            chunk_file.write_text(
                '{"accession":"b","text":"Evidence B from the prospectus."}\n',
                encoding="utf-8",
            )
            index = root / "chunk_index.csv"
            pd.DataFrame([
                {"accession": "b", "chunk_file": "data/chunks/sample.jsonl"}
            ]).to_csv(index, index=False)
            question = dict(self.question)
            question["expected_deal_ids"] = ["b"]
            question["supporting_passages"] = [
                {"accession": "b", "quote": "Evidence B from the prospectus."}
            ]

            validate_supporting_passages([question], index, chunks)


if __name__ == "__main__":
    unittest.main()
