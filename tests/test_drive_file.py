"""Tests for the Google Drive zip-file download endpoint (routers/drive_file)."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError


def _make_http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


def _patch_key_exists(exists: bool = True):
    mock_path = MagicMock()
    mock_path.exists.return_value = exists
    return patch("routers.drive_file.SERVICE_ACCOUNT_KEY_PATH", mock_path)


def _make_service(filename: str = "archive.zip") -> MagicMock:
    service = MagicMock()
    service.files.return_value.get.return_value.execute.return_value = {"name": filename}
    service.files.return_value.get_media.return_value = MagicMock()
    return service


def _make_downloader(chunks: list[bytes]):
    """Return a MediaIoBaseDownload factory that yields the given chunks into fd."""
    call_count = 0

    def factory(fd, request, chunksize=None):
        nonlocal call_count
        mock = MagicMock()

        def next_chunk():
            nonlocal call_count
            call_count += 1
            data = chunks[call_count - 1]
            fd.write(data)
            done = call_count >= len(chunks)
            return None, done

        mock.next_chunk.side_effect = next_chunk
        return mock

    return factory


class TestDriveFileEndpoint:

    def test_successful_download(self):
        """Returns 200, application/zip, and the file bytes."""
        fake_zip = b"PK\x03\x04fake zip content"
        service = _make_service("scores.zip")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([fake_zip])):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 200
        assert resp.content == fake_zip
        assert resp.headers["content-type"] == "application/zip"

    def test_content_disposition_uses_drive_filename(self):
        """Content-Disposition attachment filename comes from Drive metadata."""
        service = _make_service("my_scores.zip")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([b""])):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert 'attachment' in resp.headers["content-disposition"]
        assert 'filename="my_scores.zip"' in resp.headers["content-disposition"]

    def test_no_credentials_returns_503(self):
        """When credentials.json is absent, returns 503 before touching Drive."""
        with _patch_key_exists(exists=False):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 503

    def test_metadata_404_returns_404(self):
        """Drive 404 on metadata fetch is forwarded as 404 with a helpful message."""
        service = MagicMock()
        service.files.return_value.get.return_value.execute.side_effect = _make_http_error(404)

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 404
        assert "shared with the service account" in resp.json()["detail"]

    def test_metadata_non_404_error_returns_502(self):
        """Non-404 Drive errors on metadata fetch return 502."""
        service = MagicMock()
        service.files.return_value.get.return_value.execute.side_effect = _make_http_error(403)

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 502

    def test_streams_multiple_chunks(self):
        """Body is the ordered concatenation of all chunks yielded by the downloader."""
        chunk1 = b"first_part"
        chunk2 = b"second_part"
        service = _make_service("big.zip")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([chunk1, chunk2])):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 200
        assert resp.content == chunk1 + chunk2

    def test_download_error_during_streaming_aborts_connection(self):
        """HttpError raised during chunk download propagates and terminates the stream."""
        service = _make_service()

        def bad_downloader(fd, request, chunksize=None):
            mock = MagicMock()
            mock.next_chunk.side_effect = _make_http_error(500)
            return mock

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=bad_downloader):
            from server import app
            with pytest.raises(Exception):
                TestClient(app).get("/drive/file")
