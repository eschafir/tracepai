import mimetypes
import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlmodel import select

from app import ocr, storage
from app.auth import CurrentUser, DbSession
from app.documents import gps_from_image, is_pdf, read_upload, suffix, to_images
from app.models import Transaction

router = APIRouter(prefix="/receipts", tags=["receipts"])


def media_type(name: str) -> str:
    """Only images and PDFs are served as what they are, so an uploaded file can never run as a page."""
    kind = mimetypes.guess_type(name)[0] or ""
    return kind if kind.startswith("image/") or kind == "application/pdf" else "application/octet-stream"


@router.post("/scan")
def scan(file: UploadFile, user: CurrentUser):
    content = read_upload(file)
    pages = to_images(content)
    found = ocr.parse_receipt(ocr.read_text(pages))
    name = f"{user.id}-{uuid.uuid4().hex}{suffix(content)}"
    storage.save_receipt(name, content, content_type=media_type(name))
    position = None if is_pdf(content) else gps_from_image(content)
    return {
        **found,
        "lat": position[0] if position else None,
        "lng": position[1] if position else None,
        "receipt_path": name,
    }


@router.get("/{name}")
def get_receipt(name: str, db: DbSession, user: CurrentUser):
    attached = select(Transaction).where(Transaction.user_id == user.id, Transaction.receipt_path == name)
    if not storage.is_own_receipt(user.id, name) and not db.exec(attached).first():
        raise HTTPException(404, "Receipt not found")
    url = storage.get_receipt_url(name)
    if url:
        return RedirectResponse(url)
    path = storage.get_local_receipt_path(name)
    if not path:
        raise HTTPException(404, "Receipt not found")
    return FileResponse(path, media_type=media_type(name), headers={"X-Content-Type-Options": "nosniff"})
