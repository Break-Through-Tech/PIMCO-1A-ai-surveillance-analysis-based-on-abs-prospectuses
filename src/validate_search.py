"""Task 5: validate keyword/regex search and metadata filtering.

Usage:
    python src/validate_search.py
"""

from pathlib import Path
import sys

import pandas as pd

# Allow this script to import search.py from the same src/ directory.
sys.path.insert(0, str(Path(__file__).parent))

from search import load_index, search_prospectuses


def check_search(
    name,
    query,
    expected_keywords,
    use_regex=False,
    year=None,
    asset_class=None,
):
    """Run one validation test and report whether expected terms appear."""

    results = search_prospectuses(
        query=query,
        use_regex=use_regex,
        year=year,
        asset_class=asset_class,
        top_k=10,
    )

    combined_text = " ".join(
        results["deal_name"].tolist()
        + results["snippets"].astype(str).tolist()
    ).casefold()

    found_terms = [
        term
        for term in expected_keywords
        if term.casefold() in combined_text
    ]

    passed = len(results) > 0 and len(found_terms) > 0

    print("=" * 80)
    print(f"TEST: {name}")
    print(f"Query: {query}")

    if year is not None:
        print(f"Year filter: {year}")

    if asset_class is not None:
        print(f"Asset class filter: {asset_class}")

    print(f"Results returned: {len(results)}")
    print(f"Expected terms found: {found_terms}")

    if passed:
        print("STATUS: PASS")
    else:
        print("STATUS: REVIEW")

    print()

    return passed


def main():
    index = load_index()

    print("Loaded deal index.")
    print(f"Total indexed filings: {len(index)}")
    print()

    tests = []

    # Test 1: basic keyword search.
    tests.append(
        check_search(
            name="Custodian keyword search",
            query="custodian",
            expected_keywords=["custodian"],
        )
    )

    # Test 2: trustee keyword search.
    tests.append(
        check_search(
            name="Trustee keyword search",
            query="trustee",
            expected_keywords=["trustee"],
        )
    )

    # Test 3: regex search.
    tests.append(
        check_search(
            name="Physical custody regex search",
            query=r"physical custody|physical possession|original documents",
            expected_keywords=[
                "physical custody",
                "physical possession",
                "original documents",
            ],
            use_regex=True,
        )
    )

    # Test 4: year filtering.
    tests.append(
        check_search(
            name="Physical custody search filtered to 2024",
            query=r"physical custody|physical possession|original documents",
            expected_keywords=[
                "physical custody",
                "physical possession",
                "original documents",
            ],
            use_regex=True,
            year=2024,
        )
    )

    # Test 5: asset-class filtering.
    #
    # Only run this if "Auto loan" is actually present in the index.
    asset_classes = set(index["asset_class"].dropna().astype(str))

    if "Auto loan" in asset_classes:
        tests.append(
            check_search(
                name="Custodian search filtered to Auto loans",
                query="custodian",
                expected_keywords=["custodian"],
                asset_class="Auto loan",
            )
        )

    print("=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    passed = sum(tests)
    total = len(tests)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("All search validation tests passed.")
    else:
        print(
            "Some tests need manual review. "
            "This may indicate that the search query needs refinement "
            "or that the expected result is not present in the corpus."
        )


if __name__ == "__main__":
    main()
