import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import ocr, storage
from app.auth import CurrentUser
from app.documents import gps_from_image, is_pdf, to_images

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("/scan")
def scan(file: UploadFile, user: CurrentUser):
    content = file.file.read()
    pages = to_images(content)
    suffix = ".pdf" if is_pdf(content) else Path(file.filename or "").suffix.lower() or ".jpg"
    name = f"{uuid.uuid4().hex}{suffix}"
    mime = "application/pdf" if suffix == ".pdf" else file.content_type or "image/jpeg"
    storage.save_receipt(name, content, content_type=mime)
    found = ocr.parse_receipt(ocr.read_text(pages))
    position = None if is_pdf(content) else gps_from_image(content)
    return {
        **found,
        "lat": position[0] if position else None,
        "lng": position[1] if position else None,
        "receipt_path": name,
    }


@router.get("/{name}")
def get_receipt(name: str, user: CurrentUser):
    url = storage.get_receipt_url(name)
    if url:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url)
    path = storage.get_local_receipt_path(name)
    if not path:
        raise HTTPException(404, "Receipt not found")
    return FileResponse(path)
