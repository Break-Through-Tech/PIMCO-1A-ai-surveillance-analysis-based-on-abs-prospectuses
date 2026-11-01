
"""
End-to-end RAG pipeline for ABS prospectus analysis.

Workflow:
1. Receive a natural-language question.
2. Retrieve relevant passages using semantic search.
3. Generate an LLM answer using retrieved passages.
4. Validate citation references and source metadata.
5. Display the answer and its supporting SEC sources.

Usage:
    python src/rag_pipeline.py "where are collections initially deposited?"

    python src/rag_pipeline.py "are files custodied in paper form?" --issuer Toyota

    python src/rag_pipeline.py "is collateral free of liens?" --year 2025 -k 5
"""

import argparse

from answer import answer, print_result
from embed import DEFAULT_BACKEND
from validate_citations import validate_result


def run_pipeline(
    question,
    issuer=None,
    year=None,
    asset_class=None,
    top_k=8,
    backend=DEFAULT_BACKEND,
    model=None,
):
    """
    Run retrieval, answer generation, and citation validation.

    Returns:
        Dictionary containing the answer, retrieved passages,
        cited passage numbers, and citation validation results.
    """

    # Step 1: Retrieve passages and generate an LLM answer.
    result = answer(
        question=question,
        top_k=top_k,
        backend=backend,
        model=model,
        issuer=issuer,
        year=year,
        asset_class=asset_class,
    )

    # Step 2: Validate the citations and their source metadata.
    validation = validate_result(result)

    result["citation_validation"] = validation

    return result


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end ABS prospectus RAG assistant."
    )

    parser.add_argument("question", help="Question about ABS prospectuses")
    parser.add_argument("--issuer", help="Filter by issuer or deal")
    parser.add_argument("--year", help="Filter by filing year")
    parser.add_argument("--asset-class", help="Filter by asset class")
    parser.add_argument("-k", type=int, default=8)
    parser.add_argument("--backend", default=DEFAULT_BACKEND)
    parser.add_argument("--model", help="Optional LLM model override")

    args = parser.parse_args()

    if args.k < 1:
        parser.error("-k must be at least 1")

    print("\nRunning ABS Prospectus RAG Pipeline...")
    print("-" * 60)

    result = run_pipeline(
        question=args.question,
        issuer=args.issuer,
        year=args.year,
        asset_class=args.asset_class,
        top_k=args.k,
        backend=args.backend,
        model=args.model,
    )

    # Step 3: Display the generated answer and cited sources.
    print_result(result)

    # Step 4: Display citation validation.
    validation = result["citation_validation"]

    print("\n" + "=" * 60)
    print("CITATION VALIDATION")
    print("=" * 60)

    if validation["valid"]:
        print("PASS: All cited passage references and source metadata passed.")
    else:
        print("WARNING: Citation validation found issues.")

    print(f"Checked citations: {validation['checked_citations']}")
    print(f"Valid citations: {validation['valid_citations']}")
    print(f"Issues found: {len(validation['issues'])}")

    for issue in validation["issues"]:
        print(f"  - {issue}")

    print("\nPipeline completed.")


if __name__ == "__main__":
    main()
  
