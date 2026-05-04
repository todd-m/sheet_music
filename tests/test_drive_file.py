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


def _make_service(filename: str = "archive.zip", file_id: str = "resolved_id_123") -> MagicMock:
    """Build a mock Drive service that resolves FILE_NAME to the given id/filename."""
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [{"id": file_id, "name": filename}]
    }
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
        service = _make_service("hot dog stand.zip")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([fake_zip])):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 200
        assert resp.content == fake_zip
        assert resp.headers["content-type"] == "application/zip"

    def test_content_disposition_uses_drive_filename(self):
        """Content-Disposition attachment filename comes from the Drive list result."""
        service = _make_service("hot dog stand.zip")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([b""])):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert "attachment" in resp.headers["content-disposition"]
        assert 'filename="hot dog stand.zip"' in resp.headers["content-disposition"]

    def test_no_credentials_returns_503(self):
        """When credentials.json is absent, returns 503 before touching Drive."""
        with _patch_key_exists(exists=False):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 503

    def test_file_not_found_by_name_returns_404(self):
        """Empty list result (no matching file) returns 404 with a helpful message."""
        service = MagicMock()
        service.files.return_value.list.return_value.execute.return_value = {"files": []}

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 404
        assert "shared with the service account" in resp.json()["detail"]

    def test_list_api_error_returns_502(self):
        """Drive API error during name resolution returns 502."""
        service = MagicMock()
        service.files.return_value.list.return_value.execute.side_effect = _make_http_error(403)

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 502

    def test_streams_multiple_chunks(self):
        """Body is the ordered concatenation of all chunks yielded by the downloader."""
        chunk1 = b"first_part"
        chunk2 = b"second_part"
        service = _make_service("hot dog stand.zip")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([chunk1, chunk2])):
            from server import app
            resp = TestClient(app).get("/drive/file")

        assert resp.status_code == 200
        assert resp.content == chunk1 + chunk2

    def test_resolved_id_used_for_download(self):
        """The file ID from the list result is what gets passed to get_media."""
        service = _make_service(file_id="the_real_id_456")

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([b""])):
            from server import app
            TestClient(app).get("/drive/file")

        service.files.return_value.get_media.assert_called_once_with(fileId="the_real_id_456")

    def test_folder_id_scopes_query(self):
        """When FOLDER_ID is set, the list query includes a parents filter."""
        service = _make_service()
        captured = {}

        original_list = service.files.return_value.list

        def capturing_list(**kwargs):
            captured["q"] = kwargs.get("q", "")
            return original_list(**kwargs)

        service.files.return_value.list = capturing_list

        with _patch_key_exists(), \
             patch("routers.drive_file._build_drive_service", return_value=service), \
             patch("routers.drive_file.FOLDER_ID", "folder_abc"), \
             patch("routers.drive_file.MediaIoBaseDownload", side_effect=_make_downloader([b""])):
            from server import app
            TestClient(app).get("/drive/file")

        assert "folder_abc" in captured["q"]
        assert "in parents" in captured["q"]

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
