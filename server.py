"""
Minimal FastAPI server for the sheet music library app.

Serves:
  - Static files (the SPA)
  - /api/catalog — returns catalog.json
  - /api/pdf/{drive_file_id} — proxies a Google Drive PDF to the browser

Authentication:
  If a Google service account key file exists at SERVICE_ACCOUNT_KEY_PATH,
  the server uses the Drive API with Bearer auth to fetch PDFs.  This gives
  access to any file shared with the service account's email address.

  When no key file is present (or for files not shared with the service
  account), the server falls back to the public download URL.  In that case
  the file must be publicly shared, and a resourcekey query parameter may be
  needed for certain files.
"""

import json
import logging
import os
import re
import secrets
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from routers.drive_file import router as drive_router

app = FastAPI()
log = logging.getLogger("sheet_music")

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"
APP_DIR = Path(__file__).resolve().parent / "app"
SERVICE_ACCOUNT_KEY_PATH = Path(__file__).resolve().parent / "credentials.json"

DRIVE_API_URL = "https://www.googleapis.com/drive/v3/files"
DRIVE_PUBLIC_URL = "https://drive.google.com/uc"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ── App auth token (protects content-serving endpoints) ──

TOKEN_PATH = Path(__file__).resolve().parent / "token.txt"


def _load_app_token() -> str | None:
    """Shared app token from the SHEET_MUSIC_TOKEN env var or gitignored token.txt."""
    token = os.environ.get("SHEET_MUSIC_TOKEN", "").strip()
    if token:
        return token
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text().strip() or None
    return None


def require_token(request: Request, token: str | None = None) -> None:
    """FastAPI dependency: require the shared app token on protected routes.

    Accepts `Authorization: Bearer <token>` or a `?token=` query parameter.
    Fails closed: 503 when no token is configured server-side, 401 on a
    missing or wrong token.
    """
    expected = _load_app_token()
    if not expected:
        raise HTTPException(
            503, "Auth token not configured — set SHEET_MUSIC_TOKEN or create token.txt"
        )
    supplied = token or ""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        supplied = auth_header[7:].strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "Invalid or missing auth token")


# ── Service account credentials (loaded once at import time) ──

_credentials = None


def _load_credentials():
    """Load service account credentials if the key file exists."""
    global _credentials
    if SERVICE_ACCOUNT_KEY_PATH.exists():
        from google.oauth2 import service_account

        _credentials = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_KEY_PATH),
            scopes=SCOPES,
        )
        log.info("Loaded service account credentials from %s", SERVICE_ACCOUNT_KEY_PATH)
    else:
        log.info(
            "No service account key at %s — using public download URLs",
            SERVICE_ACCOUNT_KEY_PATH,
        )


_load_credentials()


def _get_auth_header() -> dict[str, str]:
    """Return an Authorization header with a fresh access token, or {} if no credentials."""
    if _credentials is None:
        return {}
    if not _credentials.valid:
        from google.auth.transport.requests import Request

        _credentials.refresh(Request())
    return {"Authorization": f"Bearer {_credentials.token}"}


@app.get("/api/catalog")
async def get_catalog():
    if not CATALOG_PATH.exists():
        raise HTTPException(404, "catalog.json not found")
    return json.loads(CATALOG_PATH.read_text())


@app.get("/api/pdf/{drive_file_id}", dependencies=[Depends(require_token)])
async def proxy_pdf(drive_file_id: str, resourcekey: str | None = None):
    """
    Proxy a PDF from Google Drive to avoid CORS issues.

    When service account credentials are configured, uses the Drive API
    (authenticated).  Falls back to the public download URL otherwise.
    The resourcekey parameter is only needed for the public-URL fallback
    when accessing files that aren't shared with the service account.
    """
    if _credentials is not None:
        return await _proxy_pdf_authenticated(drive_file_id)
    return await _proxy_pdf_public(drive_file_id, resourcekey)


async def _proxy_pdf_authenticated(drive_file_id: str):
    """Fetch a PDF via the Drive API using service account auth."""
    url = f"{DRIVE_API_URL}/{drive_file_id}?alt=media"
    auth = _get_auth_header()

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        resp = await client.get(url, headers=auth)

    if resp.status_code == 404:
        raise HTTPException(
            404,
            "File not found — check the file ID and that it's shared with the service account",
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"Drive API error (status {resp.status_code})")

    return StreamingResponse(
        iter([resp.content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={drive_file_id}.pdf"},
    )


async def _proxy_pdf_public(drive_file_id: str, resourcekey: str | None = None):
    """Fetch a PDF via the public download URL (no auth, file must be publicly shared).

    The resourcekey parameter is passed as an X-Goog-Drive-Resource-Keys
    header when present — required for some publicly shared files.
    """
    url = f"{DRIVE_PUBLIC_URL}?id={drive_file_id}&export=download"
    headers = {}
    if resourcekey:
        headers["X-Goog-Drive-Resource-Keys"] = f"{drive_file_id}/{resourcekey}"

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        resp = await client.get(url, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(502, f"Failed to fetch PDF from Drive (status {resp.status_code})")

    content_type = resp.headers.get("content-type", "")
    if "html" in content_type:
        # Google may return an HTML "confirm download" page for large files.
        match = re.search(r"confirm=([0-9A-Za-z_-]+)", resp.text)
        if match:
            confirm_url = f"{url}&confirm={match.group(1)}"
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                resp = await client.get(confirm_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(502, "Failed to fetch PDF after confirmation")
        else:
            raise HTTPException(
                502,
                "Drive returned HTML instead of PDF — file may not be shared publicly",
            )

    return StreamingResponse(
        iter([resp.content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={drive_file_id}.pdf"},
    )


app.include_router(drive_router)

# Serve the SPA — must be last so it doesn't shadow API routes.
app.mount("/", StaticFiles(directory=str(APP_DIR), html=True), name="static")
