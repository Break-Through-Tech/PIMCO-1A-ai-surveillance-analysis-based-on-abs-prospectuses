"""Answer a question from retrieved prospectus passages, citing them.

Retrieval finds the passages; this step has an LLM read only those passages and
answer from them. The model sees each passage numbered [1]..[k] and must cite
the numbers it relied on. Outside knowledge is ruled out in the prompt, and
when the passages do not answer the question it has to say so rather than fill
the gap. A due-diligence answer with an invented provision is worse than none.

Citations are checked after the call. A number that points at no passage is
reported, not silently dropped, and the source list shows only what was cited.

Usage:
    python src/answer.py "where are collections initially deposited?" --issuer Toyota
    python src/answer.py "is the collateral free and clear of liens?" --year 2025 -k 6
    python src/answer.py "who is the custodian?" --show-prompt   # no API call

The model defaults to ANSWER_MODEL below and can be overridden with the
ANSWER_MODEL environment variable or --model. OPENAI_BASE_URL in .env points
the client at any OpenAI-compatible provider, such as OpenRouter.
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ask import WIDTH, label, wrap
from embed import DEFAULT_BACKEND, client, load_env
from semantic_search import search

# The PIMCO-provided key covers gpt-5.6-luna and gpt-6-luna for completions.
ANSWER_MODEL = "gpt-5.6-luna"
TOP_K = 8
# A passage can sit in 38 deals. Listing every one would crowd the prompt, and
# the full list is still in the result for the source section.
DEALS_IN_PROMPT = 12

SYSTEM_PROMPT = """\
You answer due-diligence questions about asset-backed securities (ABS) \
prospectuses. You are given numbered passages retrieved from SEC 424H filings. \
Answer using ONLY those passages.

Rules:
1. Every factual statement must cite the passage(s) it comes from, in square \
brackets, e.g. [2] or [1][4]. Cite only passage numbers that were provided.
2. Do not use outside knowledge about these issuers, deals, or ABS market \
practice. If something is not stated in the passages, it is unknown.
3. If the passages do not answer the question, say so plainly, beginning with \
"The retrieved passages do not answer this." Then say what they do cover, if \
anything relevant.
4. If the passages answer only part of the question, answer that part and \
state what is missing.
5. Each passage lists the deals it appears in. Name deals when it matters, and \
if different deals say different things, say which deal says what.
6. Where exact legal wording matters (conditions, caps, exceptions, \
definitions), quote the key phrase verbatim.
7. Be concise: a direct answer first, then supporting detail.\
"""


def deal_line(deal):
    date = deal.get("filing_date", "")
    return f"{label(deal)} ({date}, p{deal['page']})" if date else label(deal)


def format_passages(hits):
    """The numbered source block the model reads."""
    blocks = []
    for n, hit in enumerate(hits, 1):
        deals = [deal_line(d) for d in hit["deals"][:DEALS_IN_PROMPT]]
        extra = hit["n_deals"] - len(deals)
        if extra > 0:
            deals.append(f"and {extra} more")
        blocks.append(
            f"[{n}] Section: {hit['section_title']}\n"
            f"Appears in {hit['n_deals']} deal(s): {'; '.join(deals)}\n"
            f'"""\n{hit["text"].strip()}\n"""')
    return "\n\n".join(blocks)


def build_messages(question, hits):
    user = (f"Passages:\n\n{format_passages(hits)}\n\n"
            f"Question: {question}\n\n"
            f"Answer from the passages above, citing them by number.")
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user}]


CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def parse_citations(text, n_passages):
    """Passage numbers cited, in first-cited order, and any that are invalid."""
    cited, invalid = [], []
    for group in CITATION.findall(text):
        for num in (int(x) for x in group.split(",")):
            bucket = cited if 1 <= num <= n_passages else invalid
            if num not in bucket:
                bucket.append(num)
    return cited, invalid


def answer(question, top_k=TOP_K, model=None, backend=DEFAULT_BACKEND,
           hits=None, **filters):
    """Retrieve, ask the model, and return the answer with its sources.

    `filters` pass through to search(): issuer, year, asset_class, deal.
    Pass `hits` to answer from passages retrieved elsewhere.
    """
    load_env()
    model = model or os.environ.get("ANSWER_MODEL", ANSWER_MODEL)
    if hits is None:
        hits = search(question, backend=backend, top_k=top_k, **filters)

    result = {"question": question, "model": model, "passages": hits,
              "answer": "", "cited": [], "invalid_citations": []}
    if not hits:
        # Nothing to ground on, so no call. The model would only guess.
        result["answer"] = ("No passages matched this question and filters, "
                            "so there is nothing to answer from.")
        return result

    resp = client().chat.completions.create(
        model=model, messages=build_messages(question, hits))
    text = (resp.choices[0].message.content or "").strip()
    cited, invalid = parse_citations(text, len(hits))
    result.update(answer=text, cited=cited, invalid_citations=invalid)
    return result


def print_result(result):
    print(f"\nQ: {result['question']}")
    print("=" * WIDTH)
    wrap(result["answer"], indent="")

    if result["invalid_citations"]:
        nums = ", ".join(f"[{n}]" for n in result["invalid_citations"])
        print(f"\nWARNING: answer cites passage numbers that were never "
              f"provided: {nums}")

    if not result["cited"]:
        if result["passages"]:
            print("\n(No passages cited.)")
        return

    print("\n" + "-" * WIDTH)
    print("Sources")
    for n in result["cited"]:
        hit = result["passages"][n - 1]
        lead = hit["deals"][0]
        print(f"\n[{n}] {hit['section_title'][:70]}")
        print(f"    {deal_line(lead)}")
        if hit["n_deals"] > 1:
            others = ", ".join(label(d) for d in hit["deals"][1:4])
            more = f" +{hit['n_deals'] - 4} more" if hit["n_deals"] > 4 else ""
            print(f"    also in: {others}{more}")
        print(f"    {lead['doc_url']}")

    unused = len(result["passages"]) - len(result["cited"])
    if unused:
        print(f"\n({unused} other retrieved passage(s) were not cited.)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--issuer", help="issuer or deal name, e.g. Toyota")
    ap.add_argument("--year", help="filing year, e.g. 2025")
    ap.add_argument("--asset-class", help="e.g. 'Auto loan', CMBS")
    ap.add_argument("-k", type=int, default=TOP_K, help="passages to retrieve")
    ap.add_argument("--model", help=f"LLM to answer with, default {ANSWER_MODEL}")
    ap.add_argument("--backend", default=DEFAULT_BACKEND)
    ap.add_argument("--show-prompt", action="store_true",
                    help="print the prompt and stop, without calling the LLM")
    args = ap.parse_args()

    filters = {"issuer": args.issuer, "year": args.year,
               "asset_class": args.asset_class}
    if args.show_prompt:
        hits = search(args.question, backend=args.backend, top_k=args.k, **filters)
        for msg in build_messages(args.question, hits):
            print(f"===== {msg['role']} =====\n{msg['content']}\n")
        return

    print_result(answer(args.question, top_k=args.k, model=args.model,
                        backend=args.backend, **filters))


if __name__ == "__main__":
    main()
