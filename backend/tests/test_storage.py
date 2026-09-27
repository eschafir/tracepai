from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import storage
from app.db import RECEIPTS_DIR
from app.main import app


def test_local_storage_fallback():
    filename = "test_local.txt"
    content = b"local receipt content"
    storage.save_receipt(filename, content, content_type="text/plain")

    path = storage.get_local_receipt_path(filename)
    assert path is not None
    assert path.is_file()
    assert path.read_bytes() == content
    assert storage.get_receipt_url(filename) is None

    # Cleanup
    path.unlink(missing_ok=True)


def test_supabase_storage_upload_and_signed_url():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_client.storage.from_.return_value = mock_bucket
    mock_bucket.create_signed_url.return_value = {"signedURL": "https://supabase.co/storage/v1/object/sign/receipts/test.jpg?token=123"}

    with (
        patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "fake_service_role_key",
                "SUPABASE_RECEIPTS_BUCKET": "receipts",
            },
        ),
        patch("app.storage.get_supabase_client", return_value=mock_client),
    ):
        assert storage.is_supabase_storage_enabled() is True

        # Test upload
        storage.save_receipt("receipt_123.jpg", b"image_bytes", content_type="image/jpeg")
        mock_client.storage.from_.assert_called_with("receipts")
        mock_bucket.upload.assert_called_with(
            path="receipt_123.jpg",
            file=b"image_bytes",
            file_options={"content-type": "image/jpeg"},
        )

        # Test signed url
        url = storage.get_receipt_url("receipt_123.jpg")
        assert url == "https://supabase.co/storage/v1/object/sign/receipts/test.jpg?token=123"
        mock_bucket.create_signed_url.assert_called_with(path="receipt_123.jpg", expires_in=3600)


def test_receipt_redirect_endpoint(client):
    # When Supabase returns a signed URL, GET /api/receipts/{name} should return a redirect
    with patch("app.storage.get_receipt_url", return_value="https://supabase.co/signed/receipt.jpg"):
        res = client.get("/api/receipts/receipt.jpg", follow_redirects=False)
        assert res.status_code in (302, 307)
        assert res.headers["location"] == "https://supabase.co/signed/receipt.jpg"
