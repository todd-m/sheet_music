"""Tests for the CSV parser."""

import io
from unittest.mock import patch

import pytest
from parsers.csv_parser import parse_csv_index, _normalize_header


def _mock_open_csv(content: str):
    """Return a patch context that makes open() return a StringIO with content."""
    return patch("builtins.open", return_value=io.StringIO(content))


# ── Header normalization ──

class TestNormalizeHeader:
    @pytest.mark.parametrize("raw,expected", [
        ("Title", "title"),
        ("SONG", "title"),
        ("Song Title", "title"),
        ("song_title", "title"),
        ("Volume", "volumeId"),
        ("Book", "volumeId"),
        ("volumeId", "volumeId"),
        ("Page", "nominalPage"),
        ("nominal_page", "nominalPage"),
        ("page-number", "nominalPage"),
        ("Composer", "composer"),
        ("Arranger", "arranger"),
        ("unknown_col", None),
        ("", None),
    ])
    def test_aliases(self, raw, expected):
        assert _normalize_header(raw) == expected


# ── CSV parsing ──

class TestParseCsv:
    def test_basic_three_columns(self):
        csv_text = "Title,Book,Page\nAll Of Me,Realbk1,15\nAutumn Leaves,Realbk1,30\n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "test-csv")
        assert len(entries) == 2
        assert entries[0]["title"] == "All Of Me"
        assert entries[0]["volumeId"] == "Realbk1"
        assert entries[0]["nominalPage"] == 15
        assert entries[0]["source"] == "test-csv"
        assert entries[0]["composer"] is None
        assert entries[0]["arranger"] is None

    def test_with_composer_and_arranger(self):
        csv_text = "Song,Volume,Page,Composer,Arranger\nMy Funny Valentine,Realbk1,300,Rodgers,Evans\n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert len(entries) == 1
        assert entries[0]["composer"] == "Rodgers"
        assert entries[0]["arranger"] == "Evans"

    def test_empty_composer_becomes_none(self):
        csv_text = "Title,Book,Page,Composer\nBlues,Realbk1,10,\n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert entries[0]["composer"] is None

    def test_skips_rows_with_missing_required_fields(self):
        csv_text = (
            "Title,Book,Page\n"
            "All Of Me,Realbk1,15\n"
            ",Realbk1,20\n"
            "Blues,,10\n"
            "Test,Vol,\n"
            "Good Song,Vol2,25\n"
        )
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert len(entries) == 2
        assert entries[0]["title"] == "All Of Me"
        assert entries[1]["title"] == "Good Song"

    def test_skips_non_numeric_page(self):
        csv_text = "Title,Book,Page\nAll Of Me,Realbk1,abc\nBlues,Realbk1,10\n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert len(entries) == 1
        assert entries[0]["title"] == "Blues"

    def test_missing_required_column_raises(self):
        csv_text = "Title,Page\nAll Of Me,15\n"
        with _mock_open_csv(csv_text):
            with pytest.raises(ValueError, match="missing required columns"):
                parse_csv_index("fake.csv", "src")

    def test_whitespace_trimming(self):
        csv_text = "Title,Book,Page\n  All Of Me  , Realbk1 , 15 \n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert entries[0]["title"] == "All Of Me"
        assert entries[0]["volumeId"] == "Realbk1"

    def test_extra_columns_ignored(self):
        csv_text = "Title,Book,Page,Genre,Year\nAll Of Me,Realbk1,15,Jazz,1931\n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert len(entries) == 1
        assert "Genre" not in entries[0]

    def test_empty_csv(self):
        csv_text = "Title,Book,Page\n"
        with _mock_open_csv(csv_text):
            entries = parse_csv_index("fake.csv", "src")
        assert entries == []
