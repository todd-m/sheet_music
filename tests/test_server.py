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

    def test_catalog_includes_resource_key(self, sample_catalog):
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = json.dumps(sample_catalog)
        with patch("server.CATALOG_PATH", mock_path):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/catalog")
        data = resp.json()
        assert data["volumes"]["Realbk1"]["resourceKey"] == "rk-test-456"

    def test_catalog_not_found(self):
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        with patch("server.CATALOG_PATH", mock_path):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/catalog")
        assert resp.status_code == 404


# ── PDF proxy — public (no service account) ──

class TestPdfProxyPublic:
    """Tests for the public download fallback (no credentials)."""

    def _patch_no_credentials(self):
        return patch("server._credentials", None)

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

        with self._patch_no_credentials(), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/test_file_id")

        assert resp.status_code == 200
        assert resp.content == fake_pdf_bytes
        assert "application/pdf" in resp.headers["content-type"]

    def test_resourcekey_passed_as_header(self):
        """When ?resourcekey= is provided, the server sends X-Goog-Drive-Resource-Keys."""
        fake_pdf_bytes = b"%PDF-1.4 fake content"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.content = fake_pdf_bytes

        captured_headers = {}

        async def mock_get(url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with self._patch_no_credentials(), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/file123?resourcekey=rk-abc")

        assert resp.status_code == 200
        assert captured_headers["X-Goog-Drive-Resource-Keys"] == "file123/rk-abc"

    def test_no_resourcekey_sends_no_header(self):
        """When no ?resourcekey= is provided, no resource key header is sent."""
        fake_pdf_bytes = b"%PDF-1.4 fake content"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.content = fake_pdf_bytes

        captured_headers = {}

        async def mock_get(url, **kwargs):
            captured_headers.update(kwargs.get("headers", {}))
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with self._patch_no_credentials(), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/file123")

        assert resp.status_code == 200
        assert "X-Goog-Drive-Resource-Keys" not in captured_headers

    def test_drive_returns_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with self._patch_no_credentials(), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
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

        with self._patch_no_credentials(), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
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

        with self._patch_no_credentials(), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/large_file_id")

        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 confirmed"


# ── PDF proxy — authenticated (service account) ──

class TestPdfProxyAuthenticated:
    """Tests for the Drive API path (with service account credentials)."""

    def _make_mock_credentials(self):
        creds = MagicMock()
        creds.valid = True
        creds.token = "fake-access-token"
        return creds

    def test_uses_bearer_auth(self):
        """Authenticated path sends Authorization: Bearer header."""
        fake_pdf_bytes = b"%PDF-1.4 authenticated"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = fake_pdf_bytes

        captured = {}

        async def mock_get(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers", {})
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server._credentials", self._make_mock_credentials()), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/file123")

        assert resp.status_code == 200
        assert resp.content == fake_pdf_bytes
        assert captured["headers"]["Authorization"] == "Bearer fake-access-token"
        assert "googleapis.com/drive" in captured["url"]

    def test_resourcekey_ignored_when_authenticated(self):
        """Authenticated path ignores the resourcekey param (not needed with Drive API)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4"

        captured = {}

        async def mock_get(url, **kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server._credentials", self._make_mock_credentials()), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/file123?resourcekey=rk-abc")

        assert resp.status_code == 200
        assert "X-Goog-Drive-Resource-Keys" not in captured["headers"]

    def test_file_not_found(self):
        """Drive API 404 returns a helpful error."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server._credentials", self._make_mock_credentials()), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/bad_id")

        assert resp.status_code == 404
        assert "shared with the service account" in resp.json()["detail"]

    def test_drive_api_error(self):
        """Non-404 Drive API errors return 502."""
        mock_response = MagicMock()
        mock_response.status_code = 403

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("server._credentials", self._make_mock_credentials()), \
             patch("server.httpx.AsyncClient", return_value=mock_client):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/file123")

        assert resp.status_code == 502

    def test_refreshes_expired_token(self):
        """When credentials are expired, they get refreshed before the request."""
        creds = MagicMock()
        creds.valid = False
        creds.token = "refreshed-token"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"%PDF-1.4"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        mock_request_cls = MagicMock()
        with patch("server._credentials", creds), \
             patch("server.httpx.AsyncClient", return_value=mock_client), \
             patch.dict("sys.modules", {"google.auth.transport.requests": MagicMock(Request=mock_request_cls)}):
            from server import app
            client = TestClient(app)
            resp = client.get("/api/pdf/file123")

        assert resp.status_code == 200
        creds.refresh.assert_called_once()
