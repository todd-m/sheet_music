# Sheet Music Library

A single-page app for searching and viewing a large personal sheet music library stored as PDFs on Google Drive.

## Architecture

A **FastAPI server** proxies Google Drive PDF requests to avoid CORS issues, serves the static SPA, and exposes the catalog as an API endpoint. The app itself is a vanilla JS SPA using pdf.js from CDN, with shared logic extracted into `app/lib.js`.

## Files

| File | Purpose |
|---|---|
| `catalog.json` | The song index — hand-editable, append-friendly |
| `server.py` | FastAPI server: serves the SPA, proxies Drive PDFs |
| `app/index.html` | SPA with search + pdf.js viewer + fullscreen mode |
| `app/lib.js` | Shared JS module: search, rendering, fullscreen logic |
| `ingestion/ingest.py` | CLI tool for parsing indexes into the catalog |
| `ingestion/parsers/pdf_parser.py` | Positional column parser using pdfplumber |
| `ingestion/parsers/csv_parser.py` | Flexible CSV import with column alias mapping |

## Setup

```bash
make install          # Create venv and install server + test dependencies
make install-ingestion  # Also install ingestion dependencies
npm install           # Install JS test dependencies (jsdom)
```

### Google Drive Access

The server supports two modes for fetching PDFs from Google Drive:

#### Option 1: Service Account (recommended for private files)

This lets the server access files shared with the service account — no public links needed.

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or reuse an existing one)
3. Enable the **Google Drive API** (APIs & Services → Enable APIs)
4. Go to **IAM & Admin → Service Accounts** and create a service account
5. Create a key for the service account (JSON format) and save it as `credentials.json` in the project root (this file is gitignored)
6. Share your Google Drive folder(s) with the service account's email address (it looks like `name@project-id.iam.gserviceaccount.com`)

The server detects `credentials.json` at startup and uses the Drive API with Bearer auth automatically.

#### Option 2: Public links (no setup required)

If no `credentials.json` is present, the server falls back to fetching PDFs via public download URLs. Each Drive file must be shared as "anyone with the link can view." Some files may also require a `resourceKey`, which is passed via the catalog and forwarded as an `X-Goog-Drive-Resource-Keys` header.

## How the PDF Parser Works

Instead of splitting lines on whitespace (which breaks for multi-word titles like "All Of Me"), it uses **pdfplumber's character position data**:

1. Groups characters by y-coordinate into lines
2. Groups characters within each line into tokens by x-gaps (>4pt gap = new token)
3. Identifies the **page number** as the last all-digit token
4. Splits title from book name at the **largest x-gap** between remaining tokens — this is the natural column gutter between left-aligned titles and center-aligned book names

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

# Add or update a volume using a Google Drive share link
python ingestion/ingest.py add-volume --id Realbk1 --name "The Real Book Vol 1" \
    --url "https://drive.google.com/file/d/1aBcDeFg.../view?resourcekey=0-abc123" \
    --offset 5
```

The `--url` flag accepts a full Google Drive share link and extracts both the file ID and resource key automatically.

## Running the App

```bash
make serve   # Starts uvicorn on port 7001
```

Then open http://localhost:7001.

## Testing

```bash
make test      # Run all tests (Python + JS)
make test-py   # Python tests only (pytest)
make test-js   # JS tests only (node --test)
```

## Catalog Schema

`catalog.json` has two top-level keys:

- **`volumes`** — keyed by volume ID slug, each with: `name`, `driveFileId`, `resourceKey`, `pageOffset`, `notes`
- **`songs`** — flat array, each with: `title`, `composer`, `arranger`, `volumeId`, `nominalPage`, `source`, `addedAt`

The page offset formula: `actual_pdf_page = nominalPage + pageOffset`. If a book's "page 1" is PDF page 6, set `pageOffset: 5`.

The `resourceKey` field is only needed when accessing files via public links (Option 2 above). Files shared with the service account do not require it.

## Post-Ingestion Setup

After ingesting your index, you need to:

1. Add each volume with `ingest.py add-volume --id ... --name ... --url ...`
2. Set the correct `pageOffset` for each volume
3. Either share Drive folders with the service account, or ensure files are publicly shared
