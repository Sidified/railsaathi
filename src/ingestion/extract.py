"""Step 2b: Extract plain text from every PDF in data/raw.

- Normal PDFs: read the text layer with PyMuPDF.
- Scanned pages (almost no text): render to an image and OCR with Tesseract.
- Drop Hindi lines (we answer in English/Hinglish from the English text).
- Drop browser print headers/footers (date-time line, URL + page number).

Output: data/processed/pages.jsonl  (one JSON object per kept page)
LLM calls: 0
"""
import json
import re
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

RAW_DIR = Path("data/raw")
OUT_FILE = Path("data/processed/pages.jsonl")

MIN_WORDS_FOR_TEXT_LAYER = 20   # fewer words than this => treat page as scanned
OCR_DPI = 300
DEVANAGARI = re.compile(r"[\u0900-\u097F]")
LETTER = re.compile(r"[A-Za-z\u0900-\u097F]")

# Lines added by "Print to PDF" in the browser, e.g.
# "10/17/26, 8:20 AM Press Release Page | Press Information Bureau"
# "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2135694 1/2"
BROWSER_NOISE = [
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}, \d{1,2}:\d{2} ?[AP]M\b"),  # print date/time
    re.compile(r"^https?://\S+(\s+\d+/\d+)?$"),                     # URL line (+ page count)
    re.compile(r"^\d{1,2}/\d{1,2}$"),                                 # page count "6/8"
    re.compile(r"^Press Release Page \| Press Information Bureau$"),  # PIB page title
]


def is_hindi_line(line: str) -> bool:
    """True if more than 30% of the letters in the line are Devanagari."""
    letters = LETTER.findall(line)
    if not letters:
        return False
    hindi = sum(1 for ch in letters if DEVANAGARI.match(ch))
    return hindi / len(letters) > 0.3


def clean(text: str) -> str:
    kept = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        if is_hindi_line(line):
            continue
        line = DEVANAGARI.sub("", line).strip()   # strip stray Hindi chars from English lines
        if any(p.search(line) for p in BROWSER_NOISE):
            continue
        kept.append(line)
    return "\n".join(kept)


def ocr_page(page: pymupdf.Page) -> str:
    pix = page.get_pixmap(dpi=OCR_DPI)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    # 'eng+hin' so Hindi pages come out as real Hindi letters (then dropped),
    # instead of English-looking garbage.
    return pytesseract.image_to_string(img, lang="eng+hin")


def extract_pdf(path: Path) -> list[dict]:
    rows = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text()
            method = "text"
            if len(text.split()) < MIN_WORDS_FOR_TEXT_LAYER:
                text = ocr_page(page)
                method = "ocr"
            text = clean(text)
            # OCR pages need more words: a letterhead alone is ~20 words of noise
            min_words = 30 if method == "ocr" else 5
            if len(text.split()) < min_words:
                continue
            rows.append({"doc": path.name, "page": i, "method": method, "text": text})
    return rows


def main() -> None:
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    total_pages = 0
    print(f"{'document':58} {'kept/all':>8} {'ocr':>4} {'words':>7}")
    with OUT_FILE.open("w", encoding="utf-8") as out:
        for pdf in pdfs:
            with pymupdf.open(pdf) as d:
                n_pages = d.page_count
            rows = extract_pdf(pdf)
            for r in rows:
                out.write(json.dumps(r, ensure_ascii=False) + "\n")
            n_ocr = sum(r["method"] == "ocr" for r in rows)
            words = sum(len(r["text"].split()) for r in rows)
            total_pages += len(rows)
            print(f"{pdf.name:58} {len(rows):>3}/{n_pages:<4} {n_ocr:>4} {words:>7}")
    print(f"\n{len(pdfs)} documents -> {total_pages} pages saved to {OUT_FILE}")


if __name__ == "__main__":
    main()