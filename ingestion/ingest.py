#!/usr/bin/env python3
"""
CLI tool for ingesting song indexes into the sheet music catalog.

Usage:
    # Parse a PDF index
    python ingest.py pdf --file master-index.pdf --source "master-index"

    # Parse a CSV
    python ingest.py csv --file extra-songs.csv --source "manual-csv"

    # Remove all entries from a source
    python ingest.py remove --source "master-index"

    # List sources in the catalog
    python ingest.py sources

    # Add or update a volume's metadata
    python ingest.py add-volume --id Realbk1 --name "The Real Book Vol 1" \\
        --drive-id "1aBcDeFg..." --offset 5
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# Ensure the ingestion package is importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from parsers.pdf_parser import parse_pdf_index
from parsers.csv_parser import parse_csv_index

CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog.json"


def load_catalog(path: Path | None = None) -> dict:
    path = path or CATALOG_PATH
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {"volumes": {}, "songs": []}


def save_catalog(catalog: dict, path: Path | None = None) -> None:
    path = path or CATALOG_PATH
    with open(path, "w") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"Catalog saved to {path} ({len(catalog['songs'])} songs, {len(catalog['volumes'])} volumes)")


def cmd_pdf(args):
    print(f"Parsing PDF index: {args.file}")
    page_range = None
    if args.pages:
        start, end = args.pages.split("-")
        page_range = (int(start), int(end))

    entries = parse_pdf_index(args.file, args.source, page_range)
    print(f"  Extracted {len(entries)} entries")

    if args.dry_run:
        for e in entries[:20]:
            print(f"  {e['title']:40s} {e['volumeId']:15s} p.{e['nominalPage']}")
        if len(entries) > 20:
            print(f"  ... and {len(entries) - 20} more")
        return

    catalog = load_catalog()

    if args.replace:
        before = len(catalog["songs"])
        catalog["songs"] = [s for s in catalog["songs"] if s["source"] != args.source]
        removed = before - len(catalog["songs"])
        if removed:
            print(f"  Removed {removed} existing entries from source '{args.source}'")

    today = date.today().isoformat()
    for entry in entries:
        entry["addedAt"] = today
    catalog["songs"].extend(entries)

    # Auto-create volume stubs for any new volumeIds.
    existing_volumes = set(catalog["volumes"].keys())
    new_volumes = {e["volumeId"] for e in entries} - existing_volumes
    for vol_id in sorted(new_volumes):
        catalog["volumes"][vol_id] = {
            "name": vol_id,
            "driveFileId": "",
            "pageOffset": 0,
            "notes": "Auto-created — update driveFileId and pageOffset.",
        }
        print(f"  Created volume stub: {vol_id}")

    save_catalog(catalog)


def cmd_csv(args):
    print(f"Parsing CSV: {args.file}")
    entries = parse_csv_index(args.file, args.source)
    print(f"  Extracted {len(entries)} entries")

    if args.dry_run:
        for e in entries[:20]:
            print(f"  {e['title']:40s} {e['volumeId']:15s} p.{e['nominalPage']}")
        if len(entries) > 20:
            print(f"  ... and {len(entries) - 20} more")
        return

    catalog = load_catalog()

    if args.replace:
        before = len(catalog["songs"])
        catalog["songs"] = [s for s in catalog["songs"] if s["source"] != args.source]
        removed = before - len(catalog["songs"])
        if removed:
            print(f"  Removed {removed} existing entries from source '{args.source}'")

    today = date.today().isoformat()
    for entry in entries:
        entry["addedAt"] = today
    catalog["songs"].extend(entries)

    existing_volumes = set(catalog["volumes"].keys())
    new_volumes = {e["volumeId"] for e in entries} - existing_volumes
    for vol_id in sorted(new_volumes):
        catalog["volumes"][vol_id] = {
            "name": vol_id,
            "driveFileId": "",
            "pageOffset": 0,
            "notes": "Auto-created — update driveFileId and pageOffset.",
        }
        print(f"  Created volume stub: {vol_id}")

    save_catalog(catalog)


def cmd_remove(args):
    catalog = load_catalog()
    before = len(catalog["songs"])
    catalog["songs"] = [s for s in catalog["songs"] if s["source"] != args.source]
    removed = before - len(catalog["songs"])
    print(f"Removed {removed} entries from source '{args.source}'")
    save_catalog(catalog)


def cmd_sources(args):
    catalog = load_catalog()
    sources: dict[str, int] = {}
    for song in catalog["songs"]:
        src = song.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    if not sources:
        print("No songs in catalog.")
        return
    print(f"{'Source':<30s} {'Count':>6s}")
    print("-" * 38)
    for src, count in sorted(sources.items()):
        print(f"{src:<30s} {count:>6d}")


def cmd_add_volume(args):
    catalog = load_catalog()
    catalog["volumes"][args.id] = {
        "name": args.name or args.id,
        "driveFileId": args.drive_id or "",
        "pageOffset": args.offset,
        "notes": args.notes or "",
    }
    print(f"Volume '{args.id}' saved.")
    save_catalog(catalog)


def main():
    parser = argparse.ArgumentParser(
        description="Ingest song indexes into the sheet music catalog."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # pdf
    p_pdf = sub.add_parser("pdf", help="Parse a PDF index")
    p_pdf.add_argument("--file", required=True, help="Path to the index PDF")
    p_pdf.add_argument("--source", required=True, help="Source tag for these entries")
    p_pdf.add_argument("--pages", help="Page range to parse, e.g. '1-69'")
    p_pdf.add_argument("--replace", action="store_true",
                       help="Remove existing entries from this source before adding")
    p_pdf.add_argument("--dry-run", action="store_true",
                       help="Preview extracted entries without saving")
    p_pdf.set_defaults(func=cmd_pdf)

    # csv
    p_csv = sub.add_parser("csv", help="Parse a CSV file")
    p_csv.add_argument("--file", required=True, help="Path to the CSV file")
    p_csv.add_argument("--source", required=True, help="Source tag for these entries")
    p_csv.add_argument("--replace", action="store_true",
                       help="Remove existing entries from this source before adding")
    p_csv.add_argument("--dry-run", action="store_true",
                       help="Preview extracted entries without saving")
    p_csv.set_defaults(func=cmd_csv)

    # remove
    p_rm = sub.add_parser("remove", help="Remove all entries from a source")
    p_rm.add_argument("--source", required=True, help="Source tag to remove")
    p_rm.set_defaults(func=cmd_remove)

    # sources
    p_src = sub.add_parser("sources", help="List ingestion sources and counts")
    p_src.set_defaults(func=cmd_sources)

    # add-volume
    p_vol = sub.add_parser("add-volume", help="Add or update a volume")
    p_vol.add_argument("--id", required=True, help="Volume ID slug")
    p_vol.add_argument("--name", help="Display name")
    p_vol.add_argument("--drive-id", help="Google Drive file ID")
    p_vol.add_argument("--offset", type=int, default=0, help="PDF page offset")
    p_vol.add_argument("--notes", help="Freeform notes")
    p_vol.set_defaults(func=cmd_add_volume)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
