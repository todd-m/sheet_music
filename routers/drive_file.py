"""
Google Drive zip-file download endpoint.

Intended to become its own standalone microservice once the app is decomposed.
Routes in this module should remain self-contained (no imports from the parent
server module) to keep extraction low-friction.
"""

import io
import os
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# Name of the zip file shared with the service account on Google Drive.
FILE_NAME = "hot dog stand.zip"

# Scope the search to a specific folder to prevent name collisions.
# Set to None to search across all files visible to the service account.
FOLDER_ID = None

SERVICE_ACCOUNT_KEY_PATH = Path(__file__).resolve().parent.parent / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB per request to Drive

# Duplicated from server.py on purpose — this module stays self-contained so
# it can be extracted into its own service (see module docstring).
TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.txt"

router = APIRouter()


def _load_app_token() -> str | None:
    """Shared app token from the SHEET_MUSIC_TOKEN env var or gitignored token.txt."""
    token = os.environ.get("SHEET_MUSIC_TOKEN", "").strip()
    if token:
        return token
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text().strip() or None
    return None


def require_token(request: Request, token: str | None = None) -> None:
    """Require the shared app token (Bearer header or ?token=); fail closed."""
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


def _build_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_KEY_PATH), scopes=SCOPES
    )
    if not creds.valid:
        creds.refresh(GoogleAuthRequest())
    return build("drive", "v3", credentials=creds)


def _resolve_file(service) -> dict:
    """Return the first Drive file matching FILE_NAME as {"id": ..., "name": ...}."""
    q = f"name = '{FILE_NAME}' and trashed = false"
    if FOLDER_ID:
        q += f" and '{FOLDER_ID}' in parents"

    try:
        results = (
            service.files()
            .list(
                q=q,
                fields="files(id, name)",
                pageSize=1,
            )
            .execute()
        )
    except HttpError as e:
        raise HTTPException(502, f"Drive API error resolving file name ({e.status_code})") from e

    files = results.get("files", [])
    if not files:
        raise HTTPException(
            404,
            f"No Drive file named '{FILE_NAME}' found — "
            f"check FILE_NAME and that it is shared with the service account",
        )

    return files[0]


@router.get("/drive/file", dependencies=[Depends(require_token)])
def download_drive_file():
    if not SERVICE_ACCOUNT_KEY_PATH.exists():
        raise HTTPException(503, "Service account credentials not configured")

    service = _build_drive_service()
    file = _resolve_file(service)
    file_id = file["id"]
    filename = file["name"]

    def _iter_chunks():
        try:
            request = service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request, chunksize=CHUNK_SIZE)
            done = False
            offset = 0
            while not done:
                _, done = downloader.next_chunk()
                buf.seek(offset)
                chunk = buf.read()
                offset += len(chunk)
                yield chunk
        except HttpError as e:
            if e.status_code == 404:
                raise HTTPException(404, "File not found during download") from e
            raise HTTPException(502, f"Drive API error during download ({e.status_code})") from e

    return StreamingResponse(
        _iter_chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
