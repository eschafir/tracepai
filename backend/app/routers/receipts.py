import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import vision
from app.auth import CurrentUser
from app.db import RECEIPTS_DIR
from app.documents import is_pdf, to_images

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("/scan")
def scan(file: UploadFile, user: CurrentUser):
    content = file.file.read()
    images = to_images(content)
    suffix = ".pdf" if is_pdf(content) else Path(file.filename or "").suffix.lower() or ".jpg"
    name = f"{uuid.uuid4().hex}{suffix}"
    (RECEIPTS_DIR / name).write_bytes(content)
    extraction = vision.read_pages(images)
    first = extraction.transactions[0] if extraction.transactions else None
    return {
        "document_type": extraction.document_type,
        "count": len(extraction.transactions),
        "merchant": first.merchant if first else "",
        "date": first.date if first else None,
        "amount": first.amount if first else None,
        "kind": first.kind if first else "expense",
        "receipt_path": name,
    }


@router.get("/{name}")
def get_receipt(name: str, user: CurrentUser):
    path = RECEIPTS_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Receipt not found")
    return FileResponse(path)
