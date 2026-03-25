"""
Parser for CSV/spreadsheet song indexes.

Expected columns (case-insensitive, flexible naming):
  - title / song / song title       (required)
  - volume / book / volumeId        (required)
  - page / nominal_page / page_number (required)
  - composer                        (optional)
  - arranger                        (optional)
"""

import csv
from pathlib import Path

# Map common column header variants to canonical names.
COLUMN_ALIASES = {
    "title": "title",
    "song": "title",
    "song title": "title",
    "song_title": "title",
    "volume": "volumeId",
    "book": "volumeId",
    "volumeid": "volumeId",
    "volume_id": "volumeId",
    "page": "nominalPage",
    "nominal_page": "nominalPage",
    "page_number": "nominalPage",
    "nominalpage": "nominalPage",
    "composer": "composer",
    "arranger": "arranger",
}


def _normalize_header(header: str) -> str | None:
    return COLUMN_ALIASES.get(header.strip().lower().replace("-", "_"))


def parse_csv_index(
    csv_path: str | Path,
    source_tag: str,
) -> list[dict]:
    """
    Parse a CSV file and return catalog song entries.

    Args:
        csv_path: Path to the CSV file.
        source_tag: Tag to identify this ingestion source.

    Returns:
        List of song entry dicts ready for catalog.json.
    """
    csv_path = Path(csv_path)
    entries = []

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        # Map CSV headers to canonical field names.
        field_map = {}
        for raw_header in reader.fieldnames or []:
            canonical = _normalize_header(raw_header)
            if canonical:
                field_map[raw_header] = canonical

        required = {"title", "volumeId", "nominalPage"}
        found = set(field_map.values())
        missing = required - found
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {missing}. "
                f"Found: {list(field_map.keys())}"
            )

        for row_num, row in enumerate(reader, start=2):
            mapped = {field_map[k]: v.strip() for k, v in row.items() if k in field_map}

            title = mapped.get("title", "").strip()
            volume_id = mapped.get("volumeId", "").strip()
            page_str = mapped.get("nominalPage", "").strip()

            if not title or not volume_id or not page_str:
                continue

            try:
                nominal_page = int(page_str)
            except ValueError:
                continue

            entries.append({
                "title": title,
                "composer": mapped.get("composer") or None,
                "arranger": mapped.get("arranger") or None,
                "volumeId": volume_id,
                "nominalPage": nominal_page,
                "source": source_tag,
            })

    return entries
