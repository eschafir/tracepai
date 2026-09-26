import datetime as dt
import shutil
import time

import pytest
import pytesseract

from app import documents, ocr
from tests import fixtures

RECEIPT = """
  WHOLE FOODS MARKET
  1765 California St
  03/14/2026  12:41
  Organic Bananas      2.49
  Almond Milk          4.99
  SUBTOTAL            47.30
  TAX                  3.90
  TOTAL               51.20
  VISA ****1234       51.20
"""

SPANISH = """
SUPERMERCADO DIA
Fecha: 21-09-2026
Leche 1.250,00
IMPORTE TOTAL 12.345,67
"""


def test_parse_english_receipt():
    assert ocr.parse_receipt(RECEIPT) == {"merchant": "WHOLE FOODS MARKET", "date": dt.date(2026, 3, 14), "amount": 51.20}


def test_parse_spanish_receipt():
    assert ocr.parse_receipt(SPANISH) == {"merchant": "SUPERMERCADO DIA", "date": dt.date(2026, 9, 21), "amount": 12345.67}


def test_invoice_total_due_and_currency_after_the_number():
    invoice = "INVOICE #114\nNorthwind Hosting\nInvoice date: 2026-09-10\nSubtotal 138.00\nTOTAL DUE 149.04\nPayment due: 2026-10-10"
    assert ocr.parse_receipt(invoice) == {"merchant": "Northwind Hosting", "date": dt.date(2026, 9, 10), "amount": 149.04}
    assert ocr.parse_receipt("MERCADONA\nTOTAL      23,45 EUR")["amount"] == 23.45


def test_fallback_to_largest_amount():
    assert ocr.parse_receipt("Corner Shop\ncoffee 3.50\nmuffin 4.25")["amount"] == 4.25


def test_nothing_found():
    assert ocr.parse_receipt("") == {"merchant": "", "date": None, "amount": None}


def test_small_images_are_enlarged_in_gray():
    image = ocr.prepare(fixtures.receipt())
    assert image.mode == "L" and image.width == ocr.MIN_WIDTH


def test_scan_endpoint(client, monkeypatch):
    monkeypatch.setattr(ocr, "read_text", lambda pages: "\n".join(fixtures.RECEIPT_LINES))
    scan = client.post("/api/receipts/scan", files={"file": ("r.png", fixtures.receipt(), "image/png")}).json()
    assert scan | {"receipt_path": None} == {
        "merchant": "BLUE BOTTLE COFFEE", "date": "2026-09-21", "amount": 11.15, "lat": None, "lng": None, "receipt_path": None,
    }
    assert scan["receipt_path"].endswith(".png")
    assert client.get(f"/api/receipts/{scan['receipt_path']}").content == fixtures.receipt()

    pdf = client.post("/api/receipts/scan", files={"file": ("x.bin", fixtures.invoice_pdf(), "application/octet-stream")}).json()
    assert pdf["receipt_path"].endswith(".pdf")

    monkeypatch.setattr(ocr, "read_text", lambda pages: "")
    empty = client.post("/api/receipts/scan", files={"file": ("n.png", fixtures.not_a_document(), "image/png")}).json()
    assert (empty["merchant"], empty["date"], empty["amount"]) == ("", None, None)


def test_scan_rejects_non_documents(client):
    assert client.post("/api/receipts/scan", files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 400


def test_scan_says_when_tesseract_is_missing(client, monkeypatch):
    def missing(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", missing)
    res = client.post("/api/receipts/scan", files={"file": ("r.png", fixtures.receipt(), "image/png")})
    assert res.status_code == 503 and "Tesseract" in res.json()["detail"]


# The real Tesseract, on documents generated in tests/fixtures.py. Run with `uv run pytest -m ocr -s`.


@pytest.mark.parametrize(
    "make, merchant_word, date, amount",
    [
        (fixtures.receipt, "blue bottle", dt.date(2026, 9, 21), 11.15),
        (fixtures.phone_photo_receipt, "trader joe", dt.date(2026, 9, 18), 10.44),
        (fixtures.spanish_ticket, "mercadona", dt.date(2026, 9, 21), 23.45),
        (fixtures.invoice_pdf, "northwind", dt.date(2026, 9, 10), 149.04),
    ],
    ids=["receipt", "phone-photo", "spanish-ticket", "invoice-pdf"],
)
@pytest.mark.ocr
@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed")
def test_real_documents(make, merchant_word, date, amount):
    start = time.time()
    found = ocr.parse_receipt(ocr.read_text(documents.to_images(make())))
    print(f"\n  {found}, {time.time() - start:.1f}s")
    assert merchant_word in found["merchant"].lower() and found["date"] == date and found["amount"] == amount


@pytest.mark.ocr
@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed")
def test_real_picture_without_text():
    assert ocr.parse_receipt(ocr.read_text(documents.to_images(fixtures.not_a_document())))["amount"] is None
