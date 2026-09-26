import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import ocr
from app.auth import CurrentUser
from app.db import RECEIPTS_DIR
from app.documents import gps_from_image, is_pdf, to_images

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("/scan")
def scan(file: UploadFile, user: CurrentUser):
    content = file.file.read()
    pages = to_images(content)
    suffix = ".pdf" if is_pdf(content) else Path(file.filename or "").suffix.lower() or ".jpg"
    name = f"{uuid.uuid4().hex}{suffix}"
    (RECEIPTS_DIR / name).write_bytes(content)
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
    path = RECEIPTS_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Receipt not found")
    return FileResponse(path)
