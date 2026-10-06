"""Task 4: keyword and regex search over the deal index.

Usage:
    python src/search.py
"""

import re
from pathlib import Path

import pandas as pd


DATA = Path("data")
INDEX = DATA / "deal_index.csv"


def load_index():
    """Load the deal index created by Task 3."""
    if not INDEX.exists():
        raise FileNotFoundError(
            f"Could not find {INDEX}. Run build_index.py first."
        )

    return pd.read_csv(INDEX, dtype=str).fillna("")


def load_text(text_file):
    """Load extracted prospectus text from the path stored in deal_index.csv."""
    if not text_file:
        return ""

    path = Path(text_file)

    if not path.exists():
        return ""

    return path.read_text(encoding="utf-8", errors="replace")


def get_snippet(text, start, end, window=250):
    """Return text surrounding a search match."""
    snippet_start = max(0, start - window)
    snippet_end = min(len(text), end + window)

    snippet = text[snippet_start:snippet_end]

    # Clean up whitespace for easier reading.
    snippet = re.sub(r"\s+", " ", snippet).strip()

    if snippet_start > 0:
        snippet = "... " + snippet

    if snippet_end < len(text):
        snippet = snippet + " ..."

    return snippet


def search_prospectuses(
    query,
    df=None,
    use_regex=False,
    year=None,
    asset_class=None,
    top_k=10,
):
    """Search prospectuses using keywords or regular expressions.

    Parameters
    ----------
    query : str
        Keyword or regular expression to search for.

    df : pandas.DataFrame, optional
        Deal index. If omitted, the full deal index is loaded.

    use_regex : bool
        If True, treat query as a regular expression.
        If False, search for the exact phrase.

    year : str or int, optional
        Restrict results to a filing year.

    asset_class : str, optional
        Restrict results to an asset class.

    top_k : int
        Maximum number of results to return.

    Returns
    -------
    pandas.DataFrame
        Matching deals with metadata and supporting text snippets.
    """

    if df is None:
        df = load_index()

    results = []

    # Apply metadata filters before searching.
    filtered = df.copy()

    if year is not None:
        filtered = filtered[
            filtered["filing_year"].astype(str) == str(year)
        ]

    if asset_class is not None:
        filtered = filtered[
            filtered["asset_class"].str.casefold()
            == str(asset_class).casefold()
        ]

    # Compile the search pattern.
    if use_regex:
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
    else:
        pattern = re.compile(re.escape(query), re.IGNORECASE)

    for _, row in filtered.iterrows():
        text = load_text(row["text_file"])

        if not text:
            continue

        matches = list(pattern.finditer(text))

        if not matches:
            continue

        # Return the first few useful matching passages.
        snippets = [
            get_snippet(text, match.start(), match.end())
            for match in matches[:3]
        ]

        results.append(
            {
                "deal_name": row["deal_name"],
                "series": row["series"],
                "asset_class": row["asset_class"],
                "filing_date": row["filing_date"],
                "filing_year": row["filing_year"],
                "doc_url": row["doc_url"],
                "match_count": len(matches),
                "snippets": snippets,
            }
        )

    if not results:
        return pd.DataFrame(
            columns=[
                "deal_name",
                "series",
                "asset_class",
                "filing_date",
                "filing_year",
                "doc_url",
                "match_count",
                "snippets",
            ]
        )

    # Rank results by number of matches.
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(
        by="match_count",
        ascending=False,
    )

    return results_df.head(top_k).reset_index(drop=True)


def print_results(results):
    """Print search results in a readable format."""
    if results.empty:
        print("No matching prospectuses found.")
        return

    print(f"\nFound {len(results)} matching deal(s):\n")

    for i, (_, row) in enumerate(results.iterrows(), start=1):
        print("=" * 80)
        print(f"Result {i}")
        print(f"Deal: {row['deal_name']}")
        print(f"Series: {row['series']}")
        print(f"Asset class: {row['asset_class']}")
        print(f"Filing date: {row['filing_date']}")
        print(f"Matches: {row['match_count']}")
        print("\nSupporting text:")

        for snippet in row["snippets"]:
            print(f"  - {snippet}")

        print(f"\nSEC filing: {row['doc_url']}")
        print()


if __name__ == "__main__":
    # Example searches for Task 4.
    index = load_index()

    print("Example 1: keyword search")
    results = search_prospectuses(
        "custodian",
        df=index,
    )
    print_results(results)

    print("\nExample 2: regex search")
    results = search_prospectuses(
        r"physical custody|physical possession|original documents",
        df=index,
        use_regex=True,
    )
    print_results(results)

    print("\nExample 3: regex search with metadata filtering")
    results = search_prospectuses(
        r"physical custody|physical possession|original documents",
        df=index,
        use_regex=True,
        year=2024,
    )
    print_results(results)
