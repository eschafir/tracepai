import datetime as dt

from app.ocr import parse_receipt

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
    assert parse_receipt(RECEIPT) == {"merchant": "WHOLE FOODS MARKET", "date": dt.date(2026, 3, 14), "amount": 51.20}


def test_parse_spanish_receipt():
    assert parse_receipt(SPANISH) == {"merchant": "SUPERMERCADO DIA", "date": dt.date(2026, 9, 21), "amount": 12345.67}


def test_fallback_to_largest_amount():
    assert parse_receipt("Corner Shop\ncoffee 3.50\nmuffin 4.25")["amount"] == 4.25


def test_nothing_found():
    assert parse_receipt("") == {"merchant": "", "date": None, "amount": None}
