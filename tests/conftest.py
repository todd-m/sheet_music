import copy
import json
import sys
from pathlib import Path

import pytest

# Make ingestion package importable from tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))

EMPTY_CATALOG = {"volumes": {}, "songs": []}

SAMPLE_CATALOG = {
    "volumes": {
        "Realbk1": {
            "name": "The Real Book Vol 1",
            "driveFileId": "abc123",
            "pageOffset": 5,
            "notes": "",
        }
    },
    "songs": [
        {
            "title": "All Of Me",
            "composer": None,
            "arranger": None,
            "volumeId": "Realbk1",
            "nominalPage": 15,
            "source": "master-index",
            "addedAt": "2026-01-01",
        },
        {
            "title": "Autumn Leaves",
            "composer": None,
            "arranger": None,
            "volumeId": "Realbk1",
            "nominalPage": 30,
            "source": "master-index",
            "addedAt": "2026-01-01",
        },
        {
            "title": "Jingle Bells",
            "composer": None,
            "arranger": None,
            "volumeId": "Xmas1",
            "nominalPage": 5,
            "source": "other-source",
            "addedAt": "2026-02-01",
        },
    ],
}


@pytest.fixture
def empty_catalog():
    """Return a fresh deep copy of an empty catalog dict."""
    return copy.deepcopy(EMPTY_CATALOG)


@pytest.fixture
def sample_catalog():
    """Return a fresh deep copy of a catalog with sample data."""
    return copy.deepcopy(SAMPLE_CATALOG)
