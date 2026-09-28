import io

import pypdfium2
from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PAGES = 8
MAX_SIDE = 1600
MAX_UPLOAD = 15 * 1024 * 1024


def read_upload(file: UploadFile) -> bytes:
    content = file.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, f"Files can be up to {MAX_UPLOAD // (1024 * 1024)} MB.")
    return content


def _png(image: Image.Image) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def is_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF-")


def suffix(content: bytes) -> str:
    """The file extension for an upload that to_images accepted, from its content and never from its name."""
    if is_pdf(content):
        return ".pdf"
    image_format = Image.open(io.BytesIO(content)).format
    return ".jpg" if image_format in ("JPEG", "MPO") else f".{image_format.lower()}"


def to_images(content: bytes) -> list[bytes]:
    """Turn an uploaded photo, image or PDF into one PNG per page."""
    if is_pdf(content):
        pdf = pypdfium2.PdfDocument(content)
        if len(pdf) > MAX_PAGES:
            raise HTTPException(400, f"Split statements longer than {MAX_PAGES} pages.")
        return [_png(page.render(scale=2).to_pil()) for page in pdf]
    try:
        image = Image.open(io.BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(400, "Upload a photo, an image or a PDF.")
    return [_png(ImageOps.exif_transpose(image))]


def gps_from_image(content: bytes) -> tuple[float, float] | None:
    """The position stored in a photo's EXIF GPS data, if the phone kept it."""
    try:
        gps = Image.open(io.BytesIO(content)).getexif().get_ifd(0x8825)
        lat, lng = gps[2], gps[4]
    except (UnidentifiedImageError, OSError, KeyError):
        return None

    def degrees(dms) -> float:
        d, m, s = (float(x) for x in dms)
        return d + m / 60 + s / 3600

    lat, lng = degrees(lat), degrees(lng)
    if gps.get(1) == "S":
        lat = -lat
    if gps.get(3) == "W":
        lng = -lng
    return (round(lat, 6), round(lng, 6)) if -90 <= lat <= 90 and -180 <= lng <= 180 else None
