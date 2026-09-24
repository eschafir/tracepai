"""Runs the real vision model through Ollama. Slow: run with `uv run pytest -m model -s`."""

import datetime as dt
import json
import time
import urllib.request

import pytest

from app import documents, vision
from tests import fixtures


def model_available() -> bool:
    try:
        with urllib.request.urlopen(f"{vision.OLLAMA_URL}/api/tags", timeout=3) as res:
            return any(m["name"] == vision.MODEL for m in json.load(res)["models"])
    except OSError:
        return False


pytestmark = [
    pytest.mark.model,
    pytest.mark.skipif(not model_available(), reason=f"Ollama with {vision.MODEL} is not available"),
]


def read(content: bytes) -> vision.Extraction:
    start = time.time()
    result = vision.read_pages(documents.to_images(content))
    print(f"\n  {result.document_type}, {len(result.transactions)} rows, {time.time() - start:.1f}s")
    return result


@pytest.mark.parametrize(
    "make, document_type, merchant_word, date, amount",
    [
        (fixtures.receipt, "receipt", "blue bottle", dt.date(2026, 9, 21), 11.15),
        (fixtures.phone_photo_receipt, "receipt", "trader joe", dt.date(2026, 9, 18), 10.44),
        (fixtures.spanish_ticket, "receipt", "mercadona", dt.date(2026, 9, 21), 23.45),
        (fixtures.invoice_pdf, "invoice", "northwind", dt.date(2026, 9, 10), 149.04),
    ],
    ids=["receipt", "phone-photo", "spanish-ticket", "invoice-pdf"],
)
def test_single_documents(make, document_type, merchant_word, date, amount):
    result = read(make())
    assert result.document_type == document_type
    assert len(result.transactions) == 1
    row = result.transactions[0]
    assert (row.date, row.amount, row.kind) == (date, amount, "expense")
    assert merchant_word in row.merchant.lower()


def test_bank_statement_pdf():
    result = read(fixtures.statement_pdf())
    assert result.document_type == "bank_statement"
    got = [(r.date.isoformat() if r.date else None, r.amount, r.kind) for r in result.transactions]
    expected = [(d, out or deposit, "expense" if out else "income") for d, _, out, deposit in fixtures.STATEMENT_ROWS]
    assert got == expected
    assert not any("balance" in r.merchant.lower() for r in result.transactions)


def test_not_a_financial_document():
    result = read(fixtures.not_a_document())
    assert result.document_type == "other" or not result.transactions
