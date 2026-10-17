"""Step 2c: Split the extracted pages into rule-sized chunks with metadata.

How it works
1. Join each document's pages into one list of lines (each line remembers its page).
2. Keep only the useful part of the document (e.g. only the refund part of a PIB release).
3. Split into sections at headings (numbered rules, FAQ questions, sub-titles).
4. If a section is too long, split it further at clause starts like "(a)" or "(1)".
5. Add metadata from data/sources.csv to every chunk.

Output: data/processed/chunks.jsonl
LLM calls: 0
"""
import csv
import json
import re
from pathlib import Path
from statistics import median

PAGES_FILE = Path("data/processed/pages.jsonl")
SOURCES_FILE = Path("data/sources.csv")
OUT_FILE = Path("data/processed/chunks.jsonl")
OVERRIDES_FILE = Path("data/rule_overrides.json")

TARGET_WORDS = 250   # start looking for a split point after this many words
MAX_WORDS = 400      # always split here, even mid-clause

NUMBERED = re.compile(r"^(\d{1,2}) ?\.\s*(\S.*)")          # "7. Cancellation of tickets ..."
CLAUSE_START = re.compile(r"^\(?([a-z]|[ivx]{1,4}|\d{1,2})\)")  # "(a)", "b)", "(iv)", "(3)"

# ---------------------------------------------------------------------------
# Per-document rules. With only 13 hand-picked documents, a small explicit
# config is more reliable than one generic splitter.
#   keep:     list of (start_regex, end_regex). Keep lines from start (inclusive)
#             to end (exclusive). end=None means until the end of the document.
#   numbered: split at "N. Heading" lines, but only if N is the next number in
#             sequence (stops list items like "1." inside rule 12 from splitting).
#   headings: extra regexes that start a new section.
# Documents not listed here are kept whole and only size-split.
# ---------------------------------------------------------------------------
DOC_RULES = {
    "2015_refund_rules_irctc_updated_2026-01.pdf": {
        "numbered": True,
    },
    "2026-01-16_gsr41e_vb_sleeper_refund.pdf": {
        "keep": [(r"^MINISTRY OF RAILWAYS$", r"^Uploaded by Dte")],
        "numbered": True,
    },
    "2026-03-24_pib_cancellation_reform.pdf": {
        "keep": [(r"^Ticket cancellation and refund$", r"^Update on Previous Reforms$")],
        "headings": [r"^Ticket cancellation and refund$", r"^Change of Train Boarding Point$"],
    },
    "2026-04_new_india_samachar_refund_slabs.pdf": {
        "keep": [(r"^Changes in Railway confirmed ticket cancellation rules", r"^Promoting Tribal Products")],
    },
    "2026-08-12_pib_railone_auto_refund.pdf": {
        "keep": [(r"^In cases of train cancellation", r"^RailOne is the Official App")],
    },
    "2025-06-11_pib_tatkal_aadhaar.pdf": {
        "keep": [(r"^Only Aadhaar authenticated", r"^Dharmendra Tewari")],
    },
    "2025-06-10_cc08_tatkal_otp.pdf": {
        "keep": [(r"^Sub:", r"^Copy to:")],
    },
    "2025-05-13_cc07_upgradation.pdf": {
        "keep": [(r"^Sub:", r"^3\. Necessary instruction")],
    },
    "2025-07-02_cc10_first_chart_timing.pdf": {
        "keep": [(r"^Sub:", r"^3\. Necessary instruction")],
    },
    "2024-10-16_cc10_arp_60_days.pdf": {
        "keep": [(r"^Sub:", r"^2\. Wide publicity")],
    },
    "2024_irctc_tatkal_faq.pdf": {
        # skip the question index at the top; answers start at "1. What are ..."
        "keep": [(r"^1\. What are the various classes", None)],
        "numbered": True,
    },
    "2026_irctc_eticket_faq.pdf": {
        # the index repeats every question; keep from the 2nd "1. What Document"
        "keep": [(r"^1\. What Document", None)],
        "keep_occurrence": 2,
        "headings": [r"^\d\.\s*\S.*\?$", r"^How to .*\?$"],
    },
    "2017_coaching_theory_luggage.pdf": {
        # training notes: ONLY the luggage chapter (other chapters have old 2017 rules)
        "keep": [(r"^CHAPTER 8:- LUGGAGE", r"^CHAPTER 9:-")],
        "headings": [
            # "Rules for Booking of Luggage -", "Booking of Television:- ..."
            # (not "Exception - ..." or "Note:-", which belong to the section above)
            r"^(?!Exception|Note)[A-Z][A-Za-z’'/ ,()]{3,60}?\s*(:\s*-|:-|:–|\s-\s|\s-$)",
            r"^Free Allowance, Marginal Allowance",
            r"^Maximum dimension",
        ],
    },
}


def load_sources() -> dict:
    with SOURCES_FILE.open(encoding="utf-8") as f:
        return {row["filename"]: row for row in csv.DictReader(f)}


def load_lines() -> dict[str, list[tuple[str, int]]]:
    """doc -> [(line, page), ...] in reading order."""
    docs: dict[str, list[tuple[str, int]]] = {}
    with PAGES_FILE.open(encoding="utf-8") as f:
        for raw in f:
            r = json.loads(raw)
            docs.setdefault(r["doc"], []).extend((ln, r["page"]) for ln in r["text"].splitlines())
    return docs


def apply_keep(lines, rules):
    if "keep" not in rules:
        return lines
    kept = []
    occurrence = rules.get("keep_occurrence", 1)
    for start, end in rules["keep"]:
        seen, inside = 0, False
        for ln, pg in lines:
            if not inside and re.search(start, ln):
                seen += 1
                if seen == occurrence:
                    inside = True
            elif inside and end and re.search(end, ln):
                break
            if inside:
                kept.append((ln, pg))
    if not kept:
        raise ValueError(f"keep markers matched nothing: {rules['keep']}")
    return kept


def split_sections(lines, rules):
    """Return [(heading, [(line, page), ...]), ...]."""
    extra = [re.compile(h) for h in rules.get("headings", [])]
    sections, heading, body = [], "Introduction", []
    expected = 1
    for ln, pg in lines:
        new_heading = None
        m = NUMBERED.match(ln)
        if rules.get("numbered") and m and int(m.group(1)) == expected:
            new_heading, expected = ln, expected + 1
        elif any(h.search(ln) for h in extra):
            new_heading = ln
        if new_heading:
            if body:
                sections.append((heading, body))
            heading, body = new_heading[:120], [(ln, pg)]
        else:
            body.append((ln, pg))
    if body:
        sections.append((heading, body))
    return sections


def size_split(body):
    """Split a long section into parts of ~TARGET..MAX words, preferring clause starts."""
    parts, cur, words = [], [], 0
    for ln, pg in body:
        n = len(ln.split())
        at_clause = bool(CLAUSE_START.match(ln))
        if cur and ((words >= TARGET_WORDS and at_clause) or words + n > MAX_WORDS):
            parts.append(cur)
            cur, words = [], 0
        cur.append((ln, pg))
        words += n
    if cur:
        parts.append(cur)
    # a tiny last piece (e.g. the end of a table) is useless alone: join it back
    if len(parts) > 1 and sum(len(ln.split()) for ln, _ in parts[-1]) < 50:
        parts[-2].extend(parts.pop())
    return parts


def apply_overrides(chunks: list[dict]) -> int:
    """Set chunk-level status / applies_to / notes from data/rule_overrides.json.

    A document marked 'partly_superseded' in sources.csv is mostly still valid,
    so its chunks start as 'current'; the overrides then mark the outdated parts.
    Every override must match exactly ONE chunk, otherwise we stop with an error
    (so a change in chunking can never silently drop a rule correction).
    """
    for c in chunks:
        c["note"], c["superseded_by"] = "", ""
        if c["status"] == "partly_superseded":
            c["status"] = "current"
    overrides = json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    for o in overrides:
        hits = [
            c for c in chunks
            if c["doc"] == o["doc"]
            and re.search(o["section"], c["section"])
            and re.search(o["text"], c["text"])
        ]
        if len(hits) != 1:
            raise ValueError(f"override matched {len(hits)} chunks (need exactly 1): {o['text']!r}")
        hits[0].update(o["set"])
    # every superseded_by entry must be a real chunk id
    ids = {c["chunk_id"] for c in chunks}
    for c in chunks:
        for newer in filter(None, (s.strip() for s in c["superseded_by"].split(";"))):
            if newer not in ids:
                raise ValueError(f"{c['chunk_id']}: superseded_by points to unknown chunk {newer!r}")
    return len(overrides)


def main() -> None:
    sources = load_sources()
    docs = load_lines()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    all_chunks = []
    for doc, lines in docs.items():
        n_doc = 0
        meta = sources[doc]
        rules = DOC_RULES.get(doc, {})
        lines = apply_keep(lines, rules)
        for heading, body in split_sections(lines, rules):
            parts = size_split(body)
            for i, part in enumerate(parts, start=1):
                text = "\n".join(ln for ln, _ in part)
                if len(text.split()) < 8:          # skip empty fragments
                    continue
                section = heading if len(parts) == 1 else f"{heading} (part {i}/{len(parts)})"
                n_doc += 1
                all_chunks.append({
                    # stable id: same document + same position -> same id on every run
                    "chunk_id": f"{doc.removesuffix('.pdf')}#{n_doc:02d}",
                    "doc": doc,
                    "title": meta["title"],
                    "section": section,
                    "pages": sorted({pg for _, pg in part}),
                    # Contextual header: the chunk says where it comes from, which
                    # helps both retrieval and the LLM when it reads the chunk.
                    "text": f"[{meta['title']}]\n[Section: {section}]\n{text}",
                    "words": len(text.split()),
                    "source_url": meta["source_url"],
                    "effective_from": meta["effective_from"],
                    "applies_to": meta["applies_to"],
                    "status": meta["status"],
                    "authority": meta["authority"],
                    "doc_type": meta["doc_type"],
                })
    n_overrides = apply_overrides(all_chunks)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"{'document':50} {'chunks':>6} {'min':>5} {'med':>5} {'max':>5}")
    for doc in docs:
        w = [c["words"] for c in all_chunks if c["doc"] == doc]
        print(f"{doc[:50]:50} {len(w):>6} {min(w):>5} {int(median(w)):>5} {max(w):>5}")
    print(f"\n{len(all_chunks)} chunks saved to {OUT_FILE}")
    print(f"{n_overrides} rule overrides applied")
    for key in ("status", "applies_to"):
        counts: dict[str, int] = {}
        for c in all_chunks:
            counts[c[key]] = counts.get(c[key], 0) + 1
        print(f"{key:>10}: {counts}")

if __name__ == "__main__":
    main()