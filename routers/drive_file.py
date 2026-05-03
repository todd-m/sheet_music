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

# ID of the zip file shared with the service account on Google Drive.
FILE_ID = "REPLACE_WITH_ACTUAL_FILE_ID"

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


# TODO: add auth
@router.get("/drive/file")
def download_drive_file():
    if not SERVICE_ACCOUNT_KEY_PATH.exists():
        raise HTTPException(503, "Service account credentials not configured")

    service = _build_drive_service()

    try:
        meta = service.files().get(fileId=FILE_ID, fields="name").execute()
    except HttpError as e:
        if e.status_code == 404:
            raise HTTPException(404, "File not found — check FILE_ID and that it is shared with the service account")
        raise HTTPException(502, f"Drive API error ({e.status_code})")
    filename = meta.get("name", f"{FILE_ID}.zip")

    def _iter_chunks():
        try:
            request = service.files().get_media(fileId=FILE_ID)
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
