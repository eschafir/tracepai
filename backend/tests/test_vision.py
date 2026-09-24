import datetime as dt
import io
import json
import urllib.error

import pytest
from fastapi import HTTPException
from PIL import Image

from app import documents, vision
from tests import fixtures


def reply(document_type="receipt", transactions=()):
    return {"message": {"content": json.dumps({"document_type": document_type, "transactions": list(transactions)})}}


@pytest.fixture
def fake_model(monkeypatch):
    """Replaces the Ollama call. Set .replies to a list of responses (dicts, or exceptions to raise)."""

    class Fake:
        replies: list = []
        requests: list = []

        def __call__(self, body):
            self.requests.append(body)
            item = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
            if isinstance(item, Exception):
                raise item
            return item

    fake = Fake()
    fake.replies, fake.requests = [], []
    monkeypatch.setattr(vision, "_chat", fake)
    return fake


def test_parse_page_normalizes_rows():
    content = json.dumps(
        {
            "document_type": "bank_statement",
            "transactions": [
                {"date": "2026-09-01", "merchant": "  ACME PAYROLL ", "amount": 5200, "direction": "money_in"},
                {"date": "09/03/2026", "merchant": "SAFEWAY", "amount": -86.42, "direction": "money_out"},
                {"date": None, "merchant": "X" * 100, "amount": "1.234,50", "direction": "sideways"},
                {"date": "2026-09-05", "merchant": "ZERO", "amount": 0},
                {"date": "2026-09-05", "merchant": "MISSING"},
                {"date": "2026-09-05", "merchant": "TEXT", "amount": "n/a"},
                "not a row",
            ],
        }
    )
    page = vision.parse_page(content)
    assert page.document_type == "bank_statement"
    assert [(r.date, r.merchant[:12], r.amount, r.kind) for r in page.transactions] == [
        (dt.date(2026, 9, 1), "ACME PAYROLL", 5200, "income"),
        (None, "SAFEWAY", 86.42, "expense"),
        (None, "X" * 12, 1234.5, "expense"),
    ]
    assert len(page.transactions[2].merchant) == 80


def test_parse_page_unknown_type_and_bad_shapes():
    assert vision.parse_page('{"document_type": "menu"}').document_type == "other"
    assert vision.parse_page('{"document_type": "receipt", "transactions": null}').transactions == []
    with pytest.raises(ValueError):
        vision.parse_page("[1, 2]")
    with pytest.raises(ValueError):
        vision.parse_page("not json")


def test_request_uses_fast_json_mode(fake_model):
    fake_model.replies = [reply(transactions=[{"date": "2026-09-21", "merchant": "Cafe", "amount": 4.5, "direction": "money_out"}])]
    vision.read_page(b"png-bytes")
    body = fake_model.requests[0]
    assert body["model"] == vision.MODEL
    assert body["think"] is False and body["format"] == "json" and body["stream"] is False
    assert body["options"]["temperature"] == 0
    assert body["messages"][0]["images"] == ["cG5nLWJ5dGVz"]


def test_retries_once_on_bad_json(fake_model):
    fake_model.replies = [{"message": {"content": "{oops"}}, reply()]
    assert vision.read_page(b"x").document_type == "receipt"
    assert len(fake_model.requests) == 2


def test_gives_up_after_two_bad_replies(fake_model):
    fake_model.replies = [{"message": {"content": "{oops"}}]
    with pytest.raises(HTTPException) as err:
        vision.read_page(b"x")
    assert err.value.status_code == 502 and len(fake_model.requests) == 2


@pytest.mark.parametrize(
    "error, status, text",
    [
        (urllib.error.URLError("Connection refused"), 503, "Open the Ollama app"),
        (urllib.error.HTTPError("u", 404, "not found", {}, None), 503, "ollama pull qwen3-vl:8b"),
        (urllib.error.HTTPError("u", 500, "boom", {}, None), 502, "error (500)"),
        (TimeoutError(), 504, "took too long"),
    ],
)
def test_ollama_errors_become_clear_messages(fake_model, error, status, text):
    fake_model.replies = [error]
    with pytest.raises(HTTPException) as err:
        vision.read_page(b"x")
    assert err.value.status_code == status and text in err.value.detail


def test_read_pages_combines_in_order(fake_model):
    row = lambda m: {"date": "2026-08-01", "merchant": m, "amount": 1, "direction": "money_out"}
    fake_model.replies = [reply("other", [row("A")]), reply("bank_statement", [row("B"), row("C")])]
    result = vision.read_pages([b"1", b"2"])
    assert result.document_type == "bank_statement"
    assert [r.merchant for r in result.transactions] == ["A", "B", "C"]


def open_png(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def test_images_are_uprighted_and_shrunk():
    image = Image.new("RGB", (300, 100), "white")
    exif = image.getexif()
    exif[0x0112] = 6  # stored sideways; viewers rotate it 90 degrees
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    assert open_png(documents.to_images(out.getvalue())[0]).size == (100, 300)

    big = io.BytesIO()
    Image.new("RGB", (3000, 1000), "white").save(big, format="PNG")
    assert open_png(documents.to_images(big.getvalue())[0]).size == (1600, 533)


def test_pdf_pages_become_images():
    pages = [fixtures.text_image([f"Page {i}"]) for i in range(3)]
    images = documents.to_images(fixtures.pdf(pages))
    assert len(images) == 3 and all(open_png(i).format == "PNG" for i in images)
    with pytest.raises(HTTPException) as err:
        documents.to_images(fixtures.pdf(pages * 3))
    assert err.value.status_code == 400 and "8 pages" in err.value.detail


def test_other_files_are_rejected():
    with pytest.raises(HTTPException) as err:
        documents.to_images(b"just some text")
    assert err.value.status_code == 400


RECEIPT = {"date": "2026-09-21", "merchant": "BLUE BOTTLE COFFEE", "amount": 11.15, "direction": "money_out"}


def test_scan_receipt_endpoint(client, fake_model):
    fake_model.replies = [reply("receipt", [RECEIPT])]
    files = {"file": ("r.png", fixtures.receipt(), "image/png")}
    scan = client.post("/api/receipts/scan", files=files).json()
    assert scan | {"receipt_path": None} == {
        "document_type": "receipt", "count": 1, "merchant": "BLUE BOTTLE COFFEE", "date": "2026-09-21",
        "amount": 11.15, "kind": "expense", "receipt_path": None,
    }
    assert scan["receipt_path"].endswith(".png")
    assert client.get(f"/api/receipts/{scan['receipt_path']}").content == fixtures.receipt()


def test_scan_pdf_invoice_and_statement(client, fake_model):
    fake_model.replies = [reply("invoice", [RECEIPT])]
    scan = client.post("/api/receipts/scan", files={"file": ("x.bin", fixtures.invoice_pdf(), "application/octet-stream")}).json()
    assert scan["receipt_path"].endswith(".pdf") and scan["document_type"] == "invoice"

    fake_model.replies = [reply("bank_statement", [RECEIPT, RECEIPT, RECEIPT])]
    scan = client.post("/api/receipts/scan", files={"file": ("s.pdf", fixtures.statement_pdf(), "application/pdf")}).json()
    assert scan["count"] == 6 and scan["document_type"] == "bank_statement"  # 3 rows on each of 2 pages


def test_scan_reports_ollama_down(client, fake_model):
    fake_model.replies = [urllib.error.URLError("refused")]
    res = client.post("/api/receipts/scan", files={"file": ("r.png", fixtures.receipt(), "image/png")})
    assert res.status_code == 503 and "Open the Ollama app" in res.json()["detail"]


def test_scan_rejects_non_documents(client):
    res = client.post("/api/receipts/scan", files={"file": ("a.txt", b"hello", "text/plain")})
    assert res.status_code == 400


def test_document_import_flow(client, fake_model):
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    wallet = next(w["id"] for w in client.get("/api/wallets").json() if w["name"] == "Checking")
    rows = [
        {"date": "2026-08-07", "merchant": "UBER *TRIP 99", "amount": 24.1, "direction": "money_out"},
        {"date": "2026-08-14", "merchant": "ZELLE FROM J SMITH", "amount": 120, "direction": "money_in"},
    ]
    fake_model.replies = [reply("bank_statement", rows)]
    preview = client.post("/api/import/document/preview", files={"file": ("s.png", fixtures.receipt(), "image/png")}).json()
    assert preview["document_type"] == "bank_statement"
    uber, zelle = preview["transactions"]
    assert uber == {"date": "2026-08-07", "merchant": "UBER *TRIP 99", "amount": 24.1, "kind": "expense", "category_id": cats["Transport"]}
    assert zelle["kind"] == "income" and zelle["category_id"] is None

    reviewed = [uber | {"amount": 25.0}, zelle, {"date": None, "merchant": "No date", "amount": 3, "kind": "expense"}]
    result = client.post("/api/import/document", json={"wallet_id": wallet, "transactions": reviewed}).json()
    assert result == {"imported": 2, "duplicates": 0, "errors": [{"row": 3, "message": "The date is missing"}]}
    saved = {t["merchant"]: t for t in client.get("/api/transactions", params={"tag": "imported"}).json()}
    assert saved["UBER *TRIP 99"]["amount"] == 25.0 and saved["UBER *TRIP 99"]["category_id"] == cats["Transport"]
    assert saved["ZELLE FROM J SMITH"]["category_id"] is None

    again = client.post("/api/import/document", json={"wallet_id": wallet, "transactions": reviewed[:2]}).json()
    assert again["imported"] == 0 and again["duplicates"] == 2
    for t in saved.values():
        client.delete(f"/api/transactions/{t['id']}")
    assert client.post("/api/import/document", json={"wallet_id": 9999, "transactions": []}).status_code == 404
