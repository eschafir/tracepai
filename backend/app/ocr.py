"""Reads receipts, tickets and invoices with Tesseract OCR (English and Spanish), then finds the merchant, date and total."""

import datetime as dt
import io
import re

import pytesseract
from fastapi import HTTPException
from PIL import Image, ImageOps

LANGUAGES = "eng+spa"
MIN_WIDTH = 1200  # small images are enlarged, since Tesseract reads text best at about 30 pixels per line

MONEY = re.compile(r"(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}|\d+[.,]\d{2})(?!\d)")
TOTAL_WORDS = re.compile(r"\b(grand\s+total|total|importe|amount|monto|a\s+pagar)\b", re.IGNORECASE)
SUBTOTAL = re.compile(r"sub\s*-?\s*total", re.IGNORECASE)
TITLE = re.compile(r"^\W*(invoice|factura|receipt|recibo|ticket|comprobante)\b", re.IGNORECASE)  # not the merchant
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b"), ("d", "m", "y")),
]


def prepare(png: bytes) -> Image.Image:
    image = ImageOps.autocontrast(Image.open(io.BytesIO(png)).convert("L"))
    if image.width < MIN_WIDTH:
        scale = MIN_WIDTH / image.width
        image = image.resize((MIN_WIDTH, round(image.height * scale)), Image.Resampling.LANCZOS)
    return image


def read_text(pages: list[bytes]) -> str:
    """The text of every page, from the PNGs made by documents.to_images."""
    try:
        return "\n".join(pytesseract.image_to_string(prepare(page), lang=LANGUAGES) for page in pages)
    except pytesseract.TesseractNotFoundError:
        raise HTTPException(503, "Tesseract isn't installed, so receipts can't be read. Rebuild the app with ./scripts/start-mac.sh.")


def parse_money(value: str) -> float:
    digits = re.sub(r"\D", "", value)
    return float(f"{digits[:-2]}.{digits[-2:]}")


def parse_date(text: str) -> dt.date | None:
    for pattern, order in DATE_PATTERNS:
        for match in pattern.finditer(text):
            parts = dict(zip(order, map(int, match.groups())))
            year = parts["y"] + 2000 if parts["y"] < 100 else parts["y"]
            day, month = parts["d"], parts["m"]
            if month > 12:
                day, month = month, day
            try:
                return dt.date(year, month, day)
            except ValueError:
                continue
    return None


def parse_amount(lines: list[str]) -> float | None:
    for line in reversed(lines):
        if TOTAL_WORDS.search(line) and not SUBTOTAL.search(line) and (amounts := MONEY.findall(line)):
            return parse_money(amounts[-1])
    amounts = [parse_money(m) for line in lines for m in MONEY.findall(line)]
    return max(amounts) if amounts else None


def parse_receipt(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = next((line for line in lines if re.search(r"[A-Za-z]{3}", line) and not TITLE.match(line)), "")
    return {"merchant": merchant[:80], "date": parse_date(text), "amount": parse_amount(lines)}
