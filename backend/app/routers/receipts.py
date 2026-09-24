import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.auth import CurrentUser
from app.db import RECEIPTS_DIR
from app.ocr import parse_receipt, read_text

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("/scan")
def scan(file: UploadFile, user: CurrentUser):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "Upload an image")
    name = f"{uuid.uuid4().hex}{Path(file.filename or '').suffix.lower() or '.jpg'}"
    path = RECEIPTS_DIR / name
    path.write_bytes(file.file.read())
    text = read_text(str(path))
    return {**parse_receipt(text), "receipt_path": name, "raw_text": text}


@router.get("/{name}")
def get_receipt(name: str, user: CurrentUser):
    path = RECEIPTS_DIR / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "Receipt not found")
    return FileResponse(path)
