# Sheet Music Library

A single-page app for searching and viewing a large personal sheet music library stored as PDFs on Google Drive.

## Architecture

A **FastAPI server** proxies Google Drive PDF requests to avoid CORS issues, serves the static SPA, and exposes the catalog as an API endpoint. The app itself is a single HTML file with inline JS/CSS using pdf.js from CDN.

## Files

| File | Purpose |
|---|---|
| `catalog.json` | The song index — hand-editable, append-friendly |
| `server.py` | FastAPI server: serves the SPA, proxies Drive PDFs |
| `app/index.html` | Single-file SPA with search + pdf.js viewer |
| `ingestion/ingest.py` | CLI tool for parsing indexes into the catalog |
| `ingestion/parsers/pdf_parser.py` | Positional column parser using pdfplumber |
| `ingestion/parsers/csv_parser.py` | Flexible CSV import with column alias mapping |

## How the PDF Parser Works

Instead of splitting lines on whitespace (which breaks for multi-word titles like "All Of Me"), it uses **pdfplumber's character position data**:

1. Groups characters by y-coordinate into lines
2. Groups characters within each line into tokens by x-gaps (>4pt gap = new token)
3. Identifies the **page number** as the last all-digit token
4. Splits title from book name at the **largest x-gap** between remaining tokens — this is the natural column gutter between left-aligned titles and center-aligned book names

## Setup

```bash
# Install ingestion dependencies
pip install -r ingestion/requirements.txt

# Install server dependencies
pip install -r requirements.txt
```

## CLI Usage

```bash
# Dry-run first to check parsing quality
python ingestion/ingest.py pdf --file your-index.pdf --source "master-index" --dry-run

# Ingest for real
python ingestion/ingest.py pdf --file your-index.pdf --source "master-index"

# Import from CSV
python ingestion/ingest.py csv --file extra-songs.csv --source "manual-csv"

# Re-ingest a source (removes old entries first)
python ingestion/ingest.py pdf --file your-index.pdf --source "master-index" --replace

# Remove all entries from a source
python ingestion/ingest.py remove --source "master-index"

# List ingestion sources and counts
python ingestion/ingest.py sources

# Add or update a volume's metadata
python ingestion/ingest.py add-volume --id Realbk1 --name "The Real Book Vol 1" \
    --drive-id "1aBcDeFg..." --offset 5
```

## Running the App

```bash
uvicorn server:app --reload
```

Then open http://localhost:8000.

## Catalog Schema

`catalog.json` has two top-level keys:

- **`volumes`** — keyed by volume ID slug, each with: `name`, `driveFileId`, `pageOffset`, `notes`
- **`songs`** — flat array, each with: `title`, `composer`, `arranger`, `volumeId`, `nominalPage`, `source`, `addedAt`

The page offset formula: `actual_pdf_page = nominalPage + pageOffset`. If a book's "page 1" is PDF page 6, set `pageOffset: 5`.

## Post-Ingestion Setup

After ingesting your index, you need to:

1. Fill in `driveFileId` for each volume in `catalog.json`
2. Set the correct `pageOffset` for each volume
3. Ensure each Drive file is shared (anyone with link → viewer)
