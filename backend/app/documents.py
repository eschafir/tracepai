import io

import pypdfium2
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PAGES = 8
MAX_SIDE = 1600


def _png(image: Image.Image) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def is_pdf(content: bytes) -> bool:
    return content.startswith(b"%PDF-")


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
