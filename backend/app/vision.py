"""Reads receipts, invoices and bank statements with a local vision model served by Ollama."""

import base64
import datetime as dt
import json
import os
import urllib.error
import urllib.request

from fastapi import HTTPException
from pydantic import BaseModel

from app.importer import parse_amount
from app.models import Kind

OLLAMA_URL = os.environ.get("TRACEPAI_OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("TRACEPAI_VISION_MODEL", "qwen3-vl:2b")
DOCUMENT_TYPES = {"receipt", "invoice", "bank_statement", "other"}

PROMPT = """You read financial documents for a personal expense tracker. Classify the document and extract its transactions.
Reply with compact JSON only, no spaces or newlines, in this shape:
{"document_type":"receipt|invoice|bank_statement|other","transactions":[{"date":"YYYY-MM-DD or null","merchant":"...","amount":12.34,"direction":"money_out|money_in"}]}
- receipt or invoice: exactly one transaction with the final total paid (after tax). merchant is the seller. direction is money_out unless it is a refund.
- bank_statement: one transaction per row. Withdrawals, card payments and debits are money_out; deposits and credits are money_in. Skip opening/closing balance rows.
- other: anything that is not a receipt, invoice or bank statement, with no transactions.
- amount is always a positive number. Copy the merchant or description as written."""


class Row(BaseModel):
    date: dt.date | None
    merchant: str
    amount: float
    kind: Kind


class Extraction(BaseModel):
    document_type: str
    transactions: list[Row]


def _chat(body: dict) -> dict:
    request = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def _call(image: bytes) -> str:
    body = {
        "model": MODEL,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {"temperature": 0},
        "messages": [{"role": "user", "content": PROMPT, "images": [base64.b64encode(image).decode()]}],
    }
    try:
        return _chat(body)["message"]["content"]
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise HTTPException(503, f"Run `ollama pull {MODEL}`, then try again.")
        raise HTTPException(502, f"Ollama returned an error ({err.code}). Try again.")
    except TimeoutError:
        raise HTTPException(504, "Reading the document took too long. Try a smaller or sharper image.")
    except urllib.error.URLError:
        raise HTTPException(503, f"Can't reach Ollama at {OLLAMA_URL}. Open the Ollama app and try again.")


def _date(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def _amount(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return abs(float(value))
    try:
        parsed = parse_amount(str(value)) if value is not None else None
    except ValueError:
        return None
    return abs(parsed) if parsed is not None else None


def parse_page(content: str) -> Extraction:
    """Validate the model's JSON. Raises ValueError when it isn't the expected shape."""
    raw = json.loads(content)
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    document_type = raw.get("document_type") if raw.get("document_type") in DOCUMENT_TYPES else "other"
    rows = []
    for item in raw.get("transactions") or []:
        if not isinstance(item, dict) or not (amount := _amount(item.get("amount"))):
            continue
        rows.append(
            Row(
                date=_date(item.get("date")),
                merchant=str(item.get("merchant") or "").strip()[:80],
                amount=round(amount, 2),
                kind=Kind.income if item.get("direction") == "money_in" else Kind.expense,
            )
        )
    return Extraction(document_type=document_type, transactions=rows)


def read_page(image: bytes) -> Extraction:
    for _ in range(2):
        try:
            return parse_page(_call(image))
        except ValueError:
            continue
    raise HTTPException(502, "The document could not be read. Try a sharper photo.")


def read_pages(images: list[bytes]) -> Extraction:
    pages = [read_page(image) for image in images]
    types = [p.document_type for p in pages]
    return Extraction(
        document_type="bank_statement" if "bank_statement" in types else types[0],
        transactions=[row for page in pages for row in page.transactions],
    )
