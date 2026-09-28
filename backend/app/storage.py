import logging
import os
from pathlib import Path

from app.db import RECEIPTS_DIR

log = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
RECEIPTS_BUCKET = os.environ.get("SUPABASE_RECEIPTS_BUCKET", "receipts")

_client = None


def is_own_receipt(user_id: int, name: str) -> bool:
    """Receipts are saved as <user id>-<random>.<ext>."""
    return name.startswith(f"{user_id}-")


def is_supabase_storage_enabled() -> bool:
    return bool(os.environ.get("SUPABASE_URL") and (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")))


def get_supabase_client():
    global _client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if _client is None and url and key:
        from supabase import create_client

        _client = create_client(url, key)
    return _client


def save_receipt(name: str, content: bytes, content_type: str | None = None) -> None:
    """Save receipt to Supabase Storage if configured; otherwise fall back to local disk."""
    if is_supabase_storage_enabled():
        client = get_supabase_client()
        bucket = os.environ.get("SUPABASE_RECEIPTS_BUCKET", "receipts")
        options = {"content-type": content_type or "application/octet-stream"}
        client.storage.from_(bucket).upload(path=name, file=content, file_options=options)
    else:
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        (RECEIPTS_DIR / name).write_bytes(content)


def get_receipt_url(name: str) -> str | None:
    """Return a temporary signed URL from Supabase Storage, or None if using local storage."""
    if is_supabase_storage_enabled():
        client = get_supabase_client()
        bucket = os.environ.get("SUPABASE_RECEIPTS_BUCKET", "receipts")
        try:
            res = client.storage.from_(bucket).create_signed_url(path=name, expires_in=3600)
            return res.get("signedURL") or res.get("signedUrl")
        except Exception as err:
            log.error("Failed to generate signed URL for receipt %s: %s", name, err)
            return None
    return None


def get_local_receipt_path(name: str) -> Path | None:
    """Return Path to local receipt file if it exists."""
    path = RECEIPTS_DIR / Path(name).name
    return path if path.is_file() else None
