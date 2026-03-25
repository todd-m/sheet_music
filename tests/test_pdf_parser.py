"""Tests for the PDF parser's line extraction and skip-line logic.

We mock pdfplumber page objects by creating fake character dicts with
positional data, matching the structure pdfplumber provides.
"""

import pytest
from parsers.pdf_parser import _is_skip_line, _extract_lines_with_positions


# ── Skip-line detection ──

class TestIsSkipLine:
    @pytest.mark.parametrize("text", [
        "Master Index",
        "  MASTER  INDEX  ",
        "master index",
    ])
    def test_skips_master_index(self, text):
        assert _is_skip_line(text) is True

    @pytest.mark.parametrize("text", [
        "Title                Book             Page",
        "  title   volume  page  ",
        "Song Title           Source          Page",
    ])
    def test_skips_header_rows(self, text):
        assert _is_skip_line(text) is True

    def test_skips_blank_lines(self):
        assert _is_skip_line("") is True
        assert _is_skip_line("   ") is True

    def test_does_not_skip_song_lines(self):
        assert _is_skip_line("All Of Me                Realbk1    15") is False
        assert _is_skip_line("My Funny Valentine") is False


# ── Fake page helpers ──

def _make_char(text: str, x0: float, top: float, char_width: float = 6.0):
    """Create a fake pdfplumber character dict."""
    return {
        "text": text,
        "x0": x0,
        "x1": x0 + char_width,
        "top": top,
    }


def _make_line_chars(text: str, x_start: float, top: float,
                     char_width: float = 6.0, gap_positions: dict | None = None):
    """
    Create a list of character dicts for a string, placed sequentially.

    gap_positions: dict mapping character index to extra gap width (in pts)
        to simulate column gutters.
    """
    gap_positions = gap_positions or {}
    chars = []
    x = x_start
    for i, ch in enumerate(text):
        x += gap_positions.get(i, 0)
        chars.append(_make_char(ch, x, top, char_width))
        x += char_width
    return chars


class FakePage:
    """Minimal mock of a pdfplumber page."""
    def __init__(self, chars, width=612.0):
        self.chars = chars
        self.width = width


# ── Line extraction ──

class TestExtractLines:
    def test_basic_three_column_line(self):
        """Simulate: 'All Of Me          Realbk1   15' with gaps."""
        top = 100.0
        chars = []
        # Title: "All Of Me" at x=50
        chars += _make_line_chars("All Of Me", x_start=50, top=top)
        # Book: "Realbk1" at x=300 (big gap after title)
        chars += _make_line_chars("Realbk1", x_start=300, top=top)
        # Page: "15" at x=500 (big gap after book)
        chars += _make_line_chars("15", x_start=500, top=top)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert len(results) == 1
        assert results[0]["title"] == "All Of Me"
        assert results[0]["book"] == "Realbk1"
        assert results[0]["nominalPage"] == 15

    def test_multi_word_title_and_book(self):
        """Title and book both have spaces."""
        top = 100.0
        chars = []
        chars += _make_line_chars("My Funny Valentine", x_start=50, top=top)
        chars += _make_line_chars("New Real 1", x_start=350, top=top)
        chars += _make_line_chars("42", x_start=520, top=top)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert len(results) == 1
        assert results[0]["title"] == "My Funny Valentine"
        assert results[0]["book"] == "New Real 1"
        assert results[0]["nominalPage"] == 42

    def test_multiple_lines_on_page(self):
        """Two song lines at different y positions."""
        chars = []
        # Line 1 at y=100
        chars += _make_line_chars("Song A", x_start=50, top=100)
        chars += _make_line_chars("Vol1", x_start=300, top=100)
        chars += _make_line_chars("10", x_start=500, top=100)
        # Line 2 at y=120
        chars += _make_line_chars("Song B", x_start=50, top=120)
        chars += _make_line_chars("Vol2", x_start=300, top=120)
        chars += _make_line_chars("20", x_start=500, top=120)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert len(results) == 2
        assert results[0]["title"] == "Song A"
        assert results[1]["title"] == "Song B"

    def test_skips_header_line(self):
        """A 'Master Index' line should be filtered out."""
        chars = []
        # Header
        chars += _make_line_chars("Master Index", x_start=200, top=50)
        # Data line
        chars += _make_line_chars("Blues", x_start=50, top=100)
        chars += _make_line_chars("Realbk1", x_start=300, top=100)
        chars += _make_line_chars("5", x_start=500, top=100)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert len(results) == 1
        assert results[0]["title"] == "Blues"

    def test_skips_line_without_page_number(self):
        """Lines where the last token isn't digits should be skipped."""
        chars = []
        chars += _make_line_chars("Some Random Text", x_start=50, top=100)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)
        assert results == []

    def test_empty_page(self):
        page = FakePage([])
        assert _extract_lines_with_positions(page) == []

    def test_single_token_title(self):
        """Title is one word, book is one word."""
        top = 100.0
        chars = []
        chars += _make_line_chars("Summertime", x_start=50, top=top)
        chars += _make_line_chars("Realbk1", x_start=300, top=top)
        chars += _make_line_chars("400", x_start=500, top=top)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert len(results) == 1
        assert results[0]["title"] == "Summertime"
        assert results[0]["book"] == "Realbk1"
        assert results[0]["nominalPage"] == 400

    def test_characters_on_same_y_within_tolerance(self):
        """Characters with y-positions within 3pts should group to one line."""
        chars = []
        # Slight y-jitter (simulating real PDFs)
        chars += _make_line_chars("Test", x_start=50, top=100.0)
        chars += _make_line_chars("Vol1", x_start=300, top=101.5)
        chars += _make_line_chars("7", x_start=500, top=100.8)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert len(results) == 1
        assert results[0]["title"] == "Test"

    def test_three_digit_page_number(self):
        top = 100.0
        chars = []
        chars += _make_line_chars("A Song", x_start=50, top=top)
        chars += _make_line_chars("BigBook", x_start=300, top=top)
        chars += _make_line_chars("999", x_start=500, top=top)

        page = FakePage(chars)
        results = _extract_lines_with_positions(page)

        assert results[0]["nominalPage"] == 999
