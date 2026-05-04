"""
Google Drive zip-file download endpoint.

Intended to become its own standalone microservice once the app is decomposed.
Routes in this module should remain self-contained (no imports from the parent
server module) to keep extraction low-friction.
"""

import io
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from google.auth.transport.requests import Request
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

router = APIRouter()


def _build_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_KEY_PATH), scopes=SCOPES
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def _resolve_file(service) -> dict:
    """Return the first Drive file matching FILE_NAME as {"id": ..., "name": ...}."""
    q = f"name = '{FILE_NAME}' and trashed = false"
    if FOLDER_ID:
        q += f" and '{FOLDER_ID}' in parents"

    try:
        results = service.files().list(
            q=q,
            fields="files(id, name)",
            pageSize=1,
        ).execute()
    except HttpError as e:
        raise HTTPException(502, f"Drive API error resolving file name ({e.status_code})")

    files = results.get("files", [])
    if not files:
        raise HTTPException(
            404,
            f"No Drive file named '{FILE_NAME}' found — check FILE_NAME and that it is shared with the service account",
        )

    return files[0]


# TODO: add auth
@router.get("/drive/file")
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
                raise HTTPException(404, "File not found during download")
            raise HTTPException(502, f"Drive API error during download ({e.status_code})")

    return StreamingResponse(
        _iter_chunks(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
