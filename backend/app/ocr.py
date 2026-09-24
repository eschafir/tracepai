import datetime as dt
import re

import pytesseract
from PIL import Image, ImageOps

MONEY = re.compile(r"(\d{1,3}(?:[.,\s]\d{3})*[.,]\d{2}|\d+[.,]\d{2})(?!\d)")
TOTAL_WORDS = re.compile(r"\b(grand\s+total|total|importe|amount|monto|a\s+pagar)\b", re.IGNORECASE)
SUBTOTAL = re.compile(r"sub\s*-?\s*total", re.IGNORECASE)
DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b"), ("d", "m", "y")),
]


def read_text(path: str) -> str:
    image = ImageOps.exif_transpose(Image.open(path)).convert("L")
    return pytesseract.image_to_string(image)


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
    merchant = next((line for line in lines if re.search(r"[A-Za-z]{3}", line)), "")
    return {"merchant": merchant[:80], "date": parse_date(text), "amount": parse_amount(lines)}
