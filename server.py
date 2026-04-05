"""
Minimal FastAPI server for the sheet music library app.

Serves:
  - Static files (the SPA)
  - /api/catalog — returns catalog.json
  - /api/pdf/{drive_file_id} — proxies a Google Drive PDF to the browser
"""

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI()

CATALOG_PATH = Path(__file__).resolve().parent / "catalog.json"
APP_DIR = Path(__file__).resolve().parent / "app"


@app.get("/api/catalog")
async def get_catalog():
    if not CATALOG_PATH.exists():
        raise HTTPException(404, "catalog.json not found")
    import json
    return json.loads(CATALOG_PATH.read_text())


@app.get("/api/pdf/{drive_file_id}")
async def proxy_pdf(drive_file_id: str, resourcekey: str | None = None):
    """
    Proxy a PDF from Google Drive to avoid CORS issues.
    Expects the file to be shared (anyone with link can view).
    """
    url = f"https://drive.google.com/uc?id={drive_file_id}&export=download"
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
        # Try the confirm pattern.
        import re
        match = re.search(r'confirm=([0-9A-Za-z_-]+)', resp.text)
        if match:
            confirm_url = f"{url}&confirm={match.group(1)}"
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                resp = await client.get(confirm_url, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(502, "Failed to fetch PDF after confirmation")
        else:
            raise HTTPException(502, "Drive returned HTML instead of PDF — file may not be shared publicly")

    return StreamingResponse(
        iter([resp.content]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={drive_file_id}.pdf"},
    )


# Serve the SPA — must be last so it doesn't shadow API routes.
app.mount("/", StaticFiles(directory=str(APP_DIR), html=True), name="static")
