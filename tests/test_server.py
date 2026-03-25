"""Tests for the FastAPI server endpoints."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient


# ── Catalog endpoint ──

class TestCatalogEndpoint:
    def test_returns_catalog(self, sample_catalog):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps(sample_catalog)
        with patch("server.CATALOG_PATH", mock_path):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert "volumes" in data
        assert "songs" in data
        assert len(data["songs"]) == 3

    def test_catalog_not_found(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch("server.CATALOG_PATH", mock_path):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/catalog")
        assert resp.status_code == 404


# ── PDF proxy endpoint ──

class TestPdfProxy:
    def test_successful_proxy(self):
        fake_pdf_bytes = b"%PDF-1.4 fake content"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.content = fake_pdf_bytes

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/test_file_id")

        assert resp.status_code == 200
        assert resp.content == fake_pdf_bytes
        assert "application/pdf" in resp.headers["content-type"]

    def test_drive_returns_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/bad_id")

        assert resp.status_code == 502

    def test_drive_returns_html_no_confirm(self):
        """When Drive returns HTML without a confirm link, we get 502."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body>No confirm link here</body></html>"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/some_id")

        assert resp.status_code == 502
        assert "not be shared publicly" in resp.json()["detail"]

    def test_drive_confirm_download_flow(self):
        """When Drive returns an HTML confirm page, the server retries with the confirm token."""
        html_response = MagicMock()
        html_response.status_code = 200
        html_response.headers = {"content-type": "text/html"}
        html_response.text = '<a href="something?confirm=t&amp;id=abc">Download</a>'

        pdf_response = MagicMock()
        pdf_response.status_code = 200
        pdf_response.headers = {"content-type": "application/pdf"}
        pdf_response.content = b"%PDF-1.4 confirmed"

        call_count = 0

        async def mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return html_response
            return pdf_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/large_file_id")

        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 confirmed"
