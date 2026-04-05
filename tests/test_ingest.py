"""Tests for the ingest CLI catalog operations.

All catalog I/O is mocked — no filesystem access.
"""

import copy
import json
from argparse import Namespace
from unittest.mock import patch, MagicMock

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))

from ingest import load_catalog, save_catalog, cmd_remove, cmd_sources, cmd_add_volume, cmd_csv, cmd_pdf, parse_drive_url


def _mock_catalog_io(catalog_data: dict):
    """
    Return a context manager that mocks load_catalog and save_catalog.

    load_catalog returns a deep copy of catalog_data.
    save_catalog captures the saved catalog into catalog_data (mutating it in place)
    so tests can inspect the result.
    """
    original = catalog_data

    def fake_load(path=None):
        return copy.deepcopy(original)

    def fake_save(catalog, path=None):
        original.clear()
        original.update(catalog)

    return patch.multiple("ingest", load_catalog=fake_load, save_catalog=fake_save)


# ── load / save ──

class TestLoadSave:
    def test_load_existing(self):
        data = json.dumps({"volumes": {}, "songs": [{"title": "A"}]})
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        with patch("builtins.open", return_value=__import__("io").StringIO(data)):
            cat = load_catalog(mock_path)
        assert len(cat["songs"]) == 1

    def test_load_missing_returns_empty(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        cat = load_catalog(mock_path)
        assert cat == {"volumes": {}, "songs": []}

    def test_save_writes_json(self):
        catalog = {"volumes": {}, "songs": [{"title": "Test"}]}
        mock_path = MagicMock()
        mock_file = __import__("io").StringIO()
        # Prevent the `with` statement from closing our StringIO
        mock_file.close = lambda: None
        with patch("builtins.open", return_value=mock_file):
            save_catalog(catalog, mock_path)
        mock_file.seek(0)
        written = json.loads(mock_file.read())
        assert written["songs"][0]["title"] == "Test"


# ── cmd_remove ──

class TestCmdRemove:
    def test_removes_matching_source(self, sample_catalog):
        args = Namespace(source="master-index")
        with _mock_catalog_io(sample_catalog):
            cmd_remove(args)
        assert len(sample_catalog["songs"]) == 1
        assert sample_catalog["songs"][0]["source"] == "other-source"

    def test_remove_nonexistent_source(self, sample_catalog):
        args = Namespace(source="does-not-exist")
        with _mock_catalog_io(sample_catalog):
            cmd_remove(args)
        assert len(sample_catalog["songs"]) == 3  # unchanged


# ── cmd_sources ──

class TestCmdSources:
    def test_lists_sources(self, sample_catalog, capsys):
        args = Namespace()
        with _mock_catalog_io(sample_catalog):
            cmd_sources(args)
        output = capsys.readouterr().out
        assert "master-index" in output
        assert "other-source" in output

    def test_empty_catalog(self, empty_catalog, capsys):
        args = Namespace()
        with _mock_catalog_io(empty_catalog):
            cmd_sources(args)
        output = capsys.readouterr().out
        assert "No songs" in output


# ── cmd_add_volume ──

class TestParseDriveUrl:
    def test_extracts_file_id_and_resource_key(self):
        url = "https://drive.google.com/file/d/0B_vQixE4WYYVeGZCM3lKYkxYRlU/view?usp=drive_link&resourcekey=0-3Yy8GUWRChar3Gl1-Cnbag"
        file_id, rk = parse_drive_url(url)
        assert file_id == "0B_vQixE4WYYVeGZCM3lKYkxYRlU"
        assert rk == "0-3Yy8GUWRChar3Gl1-Cnbag"

    def test_extracts_file_id_without_resource_key(self):
        url = "https://drive.google.com/file/d/1aBcDeFgHiJkLmNoP/view?usp=sharing"
        file_id, rk = parse_drive_url(url)
        assert file_id == "1aBcDeFgHiJkLmNoP"
        assert rk is None

    def test_raises_on_invalid_url(self):
        with pytest.raises(ValueError):
            parse_drive_url("https://example.com/not-a-drive-link")


class TestCmdAddVolume:
    def test_add_new_volume_with_url(self, empty_catalog):
        url = "https://drive.google.com/file/d/xyz789/view?usp=sharing"
        args = Namespace(id="JazzFake", name="Jazz Fakebook", url=url, offset=3, notes="test")
        with _mock_catalog_io(empty_catalog):
            cmd_add_volume(args)
        assert "JazzFake" in empty_catalog["volumes"]
        vol = empty_catalog["volumes"]["JazzFake"]
        assert vol["name"] == "Jazz Fakebook"
        assert vol["driveFileId"] == "xyz789"
        assert vol["pageOffset"] == 3
        assert vol["notes"] == "test"

    def test_url_with_resource_key(self, empty_catalog):
        url = "https://drive.google.com/file/d/abc123/view?resourcekey=rk-456"
        args = Namespace(id="Vol1", name=None, url=url, offset=0, notes=None)
        with _mock_catalog_io(empty_catalog):
            cmd_add_volume(args)
        vol = empty_catalog["volumes"]["Vol1"]
        assert vol["driveFileId"] == "abc123"
        assert vol["resourceKey"] == "rk-456"

    def test_update_existing_volume(self, sample_catalog):
        url = "https://drive.google.com/file/d/new_id/view"
        args = Namespace(id="Realbk1", name="Updated Name", url=url, offset=10, notes="updated")
        with _mock_catalog_io(sample_catalog):
            cmd_add_volume(args)
        assert sample_catalog["volumes"]["Realbk1"]["name"] == "Updated Name"
        assert sample_catalog["volumes"]["Realbk1"]["pageOffset"] == 10

    def test_defaults_name_to_id(self, empty_catalog):
        args = Namespace(id="Vol1", name=None, url=None, offset=0, notes=None)
        with _mock_catalog_io(empty_catalog):
            cmd_add_volume(args)
        assert empty_catalog["volumes"]["Vol1"]["name"] == "Vol1"
        assert empty_catalog["volumes"]["Vol1"]["driveFileId"] == ""


# ── cmd_csv ──

class TestCmdCsv:
    def test_ingest_csv(self, empty_catalog):
        fake_entries = [
            {"title": "My Song", "composer": None, "arranger": None,
             "volumeId": "Vol1", "nominalPage": 10, "source": "csv-test"},
            {"title": "Another", "composer": None, "arranger": None,
             "volumeId": "Vol2", "nominalPage": 20, "source": "csv-test"},
        ]
        args = Namespace(file="fake.csv", source="csv-test", replace=False, dry_run=False)
        with _mock_catalog_io(empty_catalog), \
             patch("ingest.parse_csv_index", return_value=fake_entries):
            cmd_csv(args)
        assert len(empty_catalog["songs"]) == 2
        assert empty_catalog["songs"][0]["title"] == "My Song"
        assert "Vol1" in empty_catalog["volumes"]
        assert "Vol2" in empty_catalog["volumes"]

    def test_csv_dry_run_does_not_modify(self, empty_catalog, capsys):
        fake_entries = [
            {"title": "My Song", "volumeId": "Vol1", "nominalPage": 10},
        ]
        args = Namespace(file="fake.csv", source="csv-test", replace=False, dry_run=True)
        with _mock_catalog_io(empty_catalog), \
             patch("ingest.parse_csv_index", return_value=fake_entries):
            cmd_csv(args)
        assert len(empty_catalog["songs"]) == 0  # unchanged

    def test_csv_replace_removes_old(self, sample_catalog):
        # Add an entry with source "csv-replace" to the starting catalog
        sample_catalog["songs"].append({
            "title": "Old Song", "composer": None, "arranger": None,
            "volumeId": "Realbk1", "nominalPage": 99,
            "source": "csv-replace", "addedAt": "2026-01-01",
        })
        fake_entries = [
            {"title": "Replacement Song", "composer": None, "arranger": None,
             "volumeId": "Realbk1", "nominalPage": 50, "source": "csv-replace"},
        ]
        args = Namespace(file="fake.csv", source="csv-replace", replace=True, dry_run=False)
        with _mock_catalog_io(sample_catalog), \
             patch("ingest.parse_csv_index", return_value=fake_entries):
            cmd_csv(args)
        # 3 original + 1 csv-replace removed + 1 replacement added = 4
        assert len(sample_catalog["songs"]) == 4
        titles = [s["title"] for s in sample_catalog["songs"]]
        assert "Replacement Song" in titles
        assert "Old Song" not in titles

    def test_csv_appends_to_existing(self, sample_catalog):
        fake_entries = [
            {"title": "Extra Song", "composer": None, "arranger": None,
             "volumeId": "NewVol", "nominalPage": 1, "source": "extra"},
        ]
        args = Namespace(file="fake.csv", source="extra", replace=False, dry_run=False)
        with _mock_catalog_io(sample_catalog), \
             patch("ingest.parse_csv_index", return_value=fake_entries):
            cmd_csv(args)
        assert len(sample_catalog["songs"]) == 4


# ── cmd_pdf ──

class TestCmdPdf:
    def test_ingest_pdf_with_mock(self, empty_catalog):
        fake_entries = [
            {"title": "Song A", "composer": None, "arranger": None,
             "volumeId": "Realbk1", "nominalPage": 10, "source": "test-pdf"},
            {"title": "Song B", "composer": None, "arranger": None,
             "volumeId": "JazzFake", "nominalPage": 20, "source": "test-pdf"},
        ]
        args = Namespace(file="fake.pdf", source="test-pdf", pages=None, replace=False, dry_run=False)
        with _mock_catalog_io(empty_catalog), \
             patch("ingest.parse_pdf_index", return_value=fake_entries):
            cmd_pdf(args)
        assert len(empty_catalog["songs"]) == 2
        assert "Realbk1" in empty_catalog["volumes"]
        assert "JazzFake" in empty_catalog["volumes"]

    def test_pdf_dry_run(self, empty_catalog, capsys):
        fake_entries = [
            {"title": "Song A", "volumeId": "Vol1", "nominalPage": 10},
        ]
        args = Namespace(file="fake.pdf", source="test", pages=None, replace=False, dry_run=True)
        with _mock_catalog_io(empty_catalog), \
             patch("ingest.parse_pdf_index", return_value=fake_entries):
            cmd_pdf(args)
        assert len(empty_catalog["songs"]) == 0

    def test_pdf_page_range_parsing(self, empty_catalog):
        args = Namespace(file="fake.pdf", source="test", pages="2-5", replace=False, dry_run=False)
        with _mock_catalog_io(empty_catalog), \
             patch("ingest.parse_pdf_index", return_value=[]) as mock_parse:
            cmd_pdf(args)
        mock_parse.assert_called_once_with("fake.pdf", "test", (2, 5))

    def test_pdf_replace(self, sample_catalog):
        fake_entries = [
            {"title": "Replaced Song", "composer": None, "arranger": None,
             "volumeId": "Realbk1", "nominalPage": 1, "source": "master-index"},
        ]
        args = Namespace(file="fake.pdf", source="master-index", pages=None, replace=True, dry_run=False)
        with _mock_catalog_io(sample_catalog), \
             patch("ingest.parse_pdf_index", return_value=fake_entries):
            cmd_pdf(args)
        # 2 master-index songs removed, 1 added, 1 other-source retained
        assert len(sample_catalog["songs"]) == 2
        titles = [s["title"] for s in sample_catalog["songs"]]
        assert "Replaced Song" in titles
        assert "Jingle Bells" in titles
