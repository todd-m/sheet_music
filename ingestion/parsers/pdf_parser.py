"""
Parser for whitespace-columnar PDF indexes (Title | Book | Page).

Uses pdfplumber's character-level positional data to detect column
boundaries, avoiding fragile whitespace splitting.
"""

import re
from pathlib import Path

import pdfplumber


# Lines matching these patterns are headers/noise — skip them.
SKIP_PATTERNS = [
    re.compile(r"master\s+index", re.IGNORECASE),
    re.compile(r"^\s*title\b.*\b(book|volume|source)\b", re.IGNORECASE),
    re.compile(r"^\s*song\b.*\b(book|volume|source)\b", re.IGNORECASE),
    re.compile(r"^\s*$"),
]


def _is_skip_line(text: str) -> bool:
    for pat in SKIP_PATTERNS:
        if pat.search(text):
            return True
    return False


def _extract_lines_with_positions(page) -> list[dict]:
    """
    Group characters into lines by y-position, then extract
    title / book / page by x-position clustering.
    """
    chars = page.chars
    if not chars:
        return []

    # Determine page width for column heuristics
    page_width = float(page.width)

    # Group characters by approximate y-position (same line).
    # Characters within 2 pts of y are considered same line.
    lines_by_y: dict[float, list] = {}
    for ch in chars:
        y = round(ch["top"], 0)
        matched = False
        for existing_y in list(lines_by_y.keys()):
            if abs(y - existing_y) < 3:
                lines_by_y[existing_y].append(ch)
                matched = True
                break
        if not matched:
            lines_by_y[y] = [ch]

    results = []
    for y in sorted(lines_by_y.keys()):
        line_chars = sorted(lines_by_y[y], key=lambda c: c["x0"])
        full_text = "".join(c["text"] for c in line_chars)

        if _is_skip_line(full_text):
            continue

        # Extract the page number: rightmost cluster of digits.
        # Find the rightmost contiguous digit sequence.
        page_num = None
        title = None
        book = None

        # Split characters into tokens by x-gaps > ~4 pts
        tokens = []
        current_token_chars = [line_chars[0]]
        for i in range(1, len(line_chars)):
            gap = line_chars[i]["x0"] - line_chars[i - 1]["x1"]
            if gap > 4:
                tokens.append(current_token_chars)
                current_token_chars = [line_chars[i]]
            else:
                current_token_chars.append(line_chars[i])
        tokens.append(current_token_chars)

        # Each token: text, x_start, x_end
        token_info = []
        for tok_chars in tokens:
            text = "".join(c["text"] for c in tok_chars).strip()
            if text:
                token_info.append({
                    "text": text,
                    "x0": tok_chars[0]["x0"],
                    "x1": tok_chars[-1]["x1"],
                })

        if not token_info:
            continue

        # Last token should be the page number (all digits)
        last = token_info[-1]
        if re.match(r"^\d+$", last["text"]):
            page_num = int(last["text"])
            token_info = token_info[:-1]
        else:
            # No valid page number — skip this line
            continue

        if not token_info:
            continue

        # Now split remaining tokens into title (left region) and book (right/center region).
        # Heuristic: the book name is the last token(s) before the page number,
        # positioned in the center-right area. Title is everything to the left.
        # We use a threshold: tokens starting past 45% of page width are "book".
        # But we also need to handle cases where title tokens might extend further.
        # Safer approach: the last contiguous cluster of tokens is the book name.

        # Find the largest gap between consecutive tokens — that separates title from book.
        if len(token_info) == 1:
            # Single token remaining — ambiguous. Treat as title with unknown book.
            title = token_info[0]["text"]
            book = ""
        else:
            max_gap = 0
            split_idx = len(token_info) - 1  # default: last token is book
            for i in range(1, len(token_info)):
                gap = token_info[i]["x0"] - token_info[i - 1]["x1"]
                if gap > max_gap:
                    max_gap = gap
                    split_idx = i

            title_tokens = token_info[:split_idx]
            book_tokens = token_info[split_idx:]

            title = " ".join(t["text"] for t in title_tokens)
            book = " ".join(t["text"] for t in book_tokens)

        if title and page_num is not None:
            results.append({
                "title": title.strip(),
                "book": book.strip(),
                "nominalPage": page_num,
            })

    return results


def parse_pdf_index(
    pdf_path: str | Path,
    source_tag: str,
    page_range: tuple[int, int] | None = None,
) -> list[dict]:
    """
    Parse a columnar PDF index and return catalog song entries.

    Args:
        pdf_path: Path to the index PDF.
        source_tag: Tag to identify this ingestion source.
        page_range: Optional (start, end) 1-indexed page range to parse.

    Returns:
        List of song entry dicts ready for catalog.json.
    """
    pdf_path = Path(pdf_path)
    entries = []

    with pdfplumber.open(pdf_path) as pdf:
        pages = pdf.pages
        if page_range:
            start, end = page_range
            pages = pages[start - 1 : end]

        for page in pages:
            lines = _extract_lines_with_positions(page)
            for line in lines:
                entries.append({
                    "title": line["title"],
                    "composer": None,
                    "arranger": None,
                    "volumeId": line["book"],
                    "nominalPage": line["nominalPage"],
                    "source": source_tag,
                })

    return entries
