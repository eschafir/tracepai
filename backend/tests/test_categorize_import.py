import datetime as dt
import json

import pytest

from app.categorize import normalize
from app.importer import guess_date_format, guess_mapping, parse_amount


def categories(client):
    return {c["name"]: c["id"] for c in client.get("/api/categories").json()}


def wallet(client, name):
    return next(w["id"] for w in client.get("/api/wallets").json() if w["name"] == name)


def test_normalize():
    assert normalize("UBER *TRIP 8821") == "uber trip"
    assert normalize("Trader Joe's #552") == "trader joe's"
    assert normalize("PG&E") == "pg&e"


def test_suggest_from_history_and_keywords(client):
    cats = categories(client)
    suggest = lambda merchant: client.get("/api/categories/suggest", params={"merchant": merchant}).json()
    assert suggest("SAFEWAY #1234") == {"category_id": cats["Groceries"], "source": "history"}
    assert suggest("Lyft ride") == {"category_id": cats["Transport"], "source": "keyword"}
    assert suggest("Zzyzx Unknown") is None

    body = {"date": dt.date.today().isoformat(), "amount": 20, "merchant": "Lyft", "category_id": cats["Dining"], "wallet_id": wallet(client, "Cash")}
    txn = client.post("/api/transactions", json=body).json()
    assert suggest("LYFT") == {"category_id": cats["Dining"], "source": "history"}
    client.delete(f"/api/transactions/{txn['id']}")


@pytest.mark.parametrize(
    "value, expected",
    [("-45.20", -45.2), ("1,234.56", 1234.56), ("1.234,56", 1234.56), ("12,5", 12.5), ("$1,200", 1200), ("(30.00)", -30), ("", None)],
)
def test_parse_amount(value, expected):
    assert parse_amount(value) == expected


def test_guesses():
    assert guess_mapping(["Posted Date", "Description", "Money Out", "Money In", "Balance"]) == {
        "date": "Posted Date",
        "merchant": "Description",
        "amount": None,
        "debit": "Money Out",
        "credit": "Money In",
    }
    assert guess_date_format(["2026-09-01", "2026-09-30"]) == "YYYY-MM-DD"
    assert guess_date_format(["09/01/2026", "09/30/2026"]) == "MM/DD/YYYY"
    assert guess_date_format(["01/09/2026", "30/09/2026"]) == "DD/MM/YYYY"
    assert guess_date_format(["nope"]) is None


STATEMENT = """Fecha;Concepto;Cargo;Abono
01/09/2026;UBER *TRIP 1;12,40;
15/09/2026;Nomina Acme;;2.500,00
02/09/2026;Blue Bottle;4,50;
02/09/2026;Blue Bottle;4,50;
31/02/2026;Broken row;1,00;
"""


def test_import_statement(client):
    files = {"file": ("statement.csv", STATEMENT.encode(), "text/csv")}
    preview = client.post("/api/import/preview", files=files).json()
    assert preview["mapping"] == {"date": "Fecha", "merchant": "Concepto", "amount": None, "debit": "Cargo", "credit": "Abono"}
    assert preview["date_format"] == "DD/MM/YYYY"
    assert preview["row_count"] == 5

    form = {"wallet_id": wallet(client, "Checking"), "mapping": json.dumps(preview["mapping"]), "date_format": "DD/MM/YYYY"}
    result = client.post("/api/import", files=files, data=form).json()
    assert result["imported"] == 4 and result["duplicates"] == 0
    assert result["errors"][0]["row"] == 6

    imported = client.get("/api/transactions", params={"tag": "imported"}).json()
    uber = next(t for t in imported if t["merchant"] == "UBER *TRIP 1")
    assert uber["amount"] == 12.4 and uber["kind"] == "expense"
    assert uber["category_id"] == categories(client)["Transport"]
    assert next(t for t in imported if t["merchant"] == "Nomina Acme")["amount"] == 2500

    again = client.post("/api/import", files=files, data=form).json()
    assert again["imported"] == 0 and again["duplicates"] == 4
    for t in imported:
        client.delete(f"/api/transactions/{t['id']}")


def test_import_signed_amounts(client):
    csv = b"Date,Description,Amount\n2026-09-03,Netflix,-15.49\n2026-09-04,Refund,20.00\n"
    files = {"file": ("s.csv", csv, "text/csv")}
    preview = client.post("/api/import/preview", files=files).json()
    form = {"wallet_id": wallet(client, "Credit card"), "mapping": json.dumps(preview["mapping"]), "date_format": preview["date_format"]}
    assert client.post("/api/import", files=files, data=form).json()["imported"] == 2
    imported = {t["merchant"]: t for t in client.get("/api/transactions", params={"tag": "imported"}).json()}
    assert imported["Netflix"]["kind"] == "expense" and imported["Refund"]["kind"] == "income"
    for t in imported.values():
        client.delete(f"/api/transactions/{t['id']}")


def test_import_rejects_non_csv(client):
    files = {"file": ("x.csv", b"\x89PNG\x00\x00", "text/csv")}
    assert client.post("/api/import/preview", files=files).status_code == 400
