import datetime as dt
import io
import json
import sqlite3
import urllib.error

import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app import db as app_db
from app import documents
from app.routers import places
from app.routers.goals import months_until
from tests import fixtures

TODAY = dt.date.today()


def wallet(client, name="Checking"):
    return next(w["id"] for w in client.get("/api/wallets").json() if w["name"] == name)


# Goals


def test_months_until():
    assert months_until(dt.date(2026, 12, 24), dt.date(2026, 9, 24)) == 3
    assert months_until(dt.date(2026, 12, 23), dt.date(2026, 9, 24)) == 2
    assert months_until(dt.date(2026, 10, 1), dt.date(2026, 9, 24)) == 1
    assert months_until(dt.date(2026, 1, 1), dt.date(2026, 9, 24)) == 1


def balances(client):
    return {w["name"]: w["balance"] for w in client.get("/api/wallets").json()}


def test_seeded_goals(client):
    goals = {g["name"]: g for g in client.get("/api/goals").json()}
    assert {"Lisbon trip", "Emergency fund"} <= set(goals)
    assert goals["Lisbon trip"]["saved"] == 1000 and goals["Lisbon trip"]["monthly_needed"] > 0
    assert goals["Emergency fund"]["saved"] == 3000
    assert goals["Emergency fund"]["target_date"] is None and goals["Emergency fund"]["monthly_needed"] is None
    assert goals["Lisbon trip"]["wallet_id"] == wallet(client, "Savings") and goals["Lisbon trip"]["transfer_count"] == 3


def test_goal_money_moves_between_wallets(client):
    checking, savings = wallet(client, "Checking"), wallet(client, "Savings")
    target = advance_months(TODAY, 3)
    goal = client.post("/api/goals", json={"name": "Laptop", "target_amount": 1500, "target_date": target.isoformat(),
                                           "color_slot": 5, "wallet_id": savings}).json()
    assert goal["saved"] == 0 and goal["percent"] == 0 and goal["months_left"] == 3 and goal["monthly_needed"] == 500
    url = f"/api/goals/{goal['id']}/contributions"
    before = balances(client)

    goal = client.post(url, json={"date": TODAY.isoformat(), "amount": 300, "direction": "in", "wallet_id": checking, "note": "Bonus"}).json()
    assert (goal["saved"], goal["percent"], goal["remaining"], goal["monthly_needed"]) == (300, 20, 1200, 400)
    after = balances(client)
    assert after["Checking"] == round(before["Checking"] - 300, 2) and after["Savings"] == round(before["Savings"] + 300, 2)

    goal = client.post(url, json={"date": TODAY.isoformat(), "amount": 100, "direction": "out", "wallet_id": checking}).json()
    assert goal["saved"] == 200
    assert balances(client)["Savings"] == round(before["Savings"] + 200, 2)

    history = client.get(url).json()
    assert [(c["amount"], c["wallet_id"]) for c in history] == [(-100, checking), (300, checking)]
    txn = next(t for t in client.get("/api/transactions", params={"q": "Laptop"}).json() if t["id"] == history[1]["id"])
    assert (txn["kind"], txn["wallet_id"], txn["to_wallet_id"], txn["goal_id"], txn["notes"]) == ("transfer", checking, savings, goal["id"], "Bonus")

    # Removing a history row deletes its transfer.
    goal = client.delete(f"/api/goals/contributions/{history[0]['id']}").json()
    assert goal["saved"] == 300
    assert balances(client)["Savings"] == round(before["Savings"] + 300, 2)

    # Editing or deleting the transfer on Transactions changes the goal.
    body = {k: v for k, v in txn.items() if k not in ("id", "recurring_id")}
    assert client.put(f"/api/transactions/{txn['id']}", json={**body, "amount": 450}).status_code == 200
    assert client.get(url).json()[0]["amount"] == 450
    wrong = client.put(f"/api/transactions/{txn['id']}", json={**body, "to_wallet_id": wallet(client, "Cash")})
    assert wrong.status_code == 422 and "Savings" in wrong.json()["detail"]
    assert client.delete(f"/api/transactions/{txn['id']}").status_code == 200
    assert client.get(url).json() == []

    # The wallet is locked once money has moved.
    client.post(url, json={"date": TODAY.isoformat(), "amount": 50, "direction": "in", "wallet_id": checking})
    edit = {"name": "New laptop", "target_amount": 2000, "color_slot": 5, "wallet_id": savings}
    edited = client.put(f"/api/goals/{goal['id']}", json=edit).json()
    assert edited["name"] == "New laptop" and edited["saved"] == 50 and edited["months_left"] is None
    assert client.put(f"/api/goals/{goal['id']}", json={**edit, "wallet_id": checking}).status_code == 422

    # Deleting the goal keeps its transfers.
    transfer_id = client.get(url).json()[0]["id"]
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 200
    assert client.get(url).status_code == 404
    kept = next(t for t in client.get("/api/transactions").json() if t["id"] == transfer_id)
    assert kept["goal_id"] is None and kept["amount"] == 50


def test_goal_validation(client):
    checking, savings = wallet(client, "Checking"), wallet(client, "Savings")
    assert client.post("/api/goals", json={"name": "X", "target_amount": 0}).status_code == 422
    assert client.post("/api/goals", json={"name": "X", "target_amount": 10, "color_slot": 9}).status_code == 422

    no_wallet = client.post("/api/goals", json={"name": "No wallet", "target_amount": 10}).json()
    add = {"date": TODAY.isoformat(), "amount": 5, "direction": "in", "wallet_id": checking}
    assert client.post(f"/api/goals/{no_wallet['id']}/contributions", json=add).status_code == 422
    # A goal without transfers can still change wallet.
    moved = client.put(f"/api/goals/{no_wallet['id']}", json={"name": "No wallet", "target_amount": 10, "wallet_id": savings})
    assert moved.status_code == 200 and moved.json()["wallet_id"] == savings

    url = f"/api/goals/{no_wallet['id']}/contributions"
    assert client.post(url, json={**add, "wallet_id": savings}).status_code == 422
    assert client.post(url, json={**add, "amount": 0}).status_code == 422
    assert client.post(url, json={**add, "direction": "sideways"}).status_code == 422

    expense = {"date": TODAY.isoformat(), "amount": 5, "kind": "expense", "wallet_id": checking, "goal_id": no_wallet["id"]}
    assert client.post("/api/transactions", json=expense).status_code == 422
    elsewhere = {**expense, "kind": "transfer", "to_wallet_id": wallet(client, "Cash")}
    assert client.post("/api/transactions", json=elsewhere).status_code == 422
    assert client.post("/api/transactions", json={**elsewhere, "goal_id": 999999}).status_code == 422
    assert client.post("/api/transactions", json={**elsewhere, "to_wallet_id": savings}).status_code == 200
    client.delete(f"/api/goals/{no_wallet['id']}")


def advance_months(date: dt.date, n: int) -> dt.date:
    import calendar
    month = date.month - 1 + n
    year, month = date.year + month // 12, month % 12 + 1
    return date.replace(year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1]))


# Places


@pytest.fixture
def fake_geocoder(monkeypatch):
    calls = []

    def fake(request, timeout):
        calls.append(request)
        if fake.error:
            raise fake.error
        return io.BytesIO(json.dumps(fake.reply).encode())

    fake.error, fake.reply = None, []
    monkeypatch.setattr(places.urllib.request, "urlopen", fake)
    fake.calls = calls
    return fake


def test_place_search(client, fake_geocoder):
    fake_geocoder.reply = [
        {"name": "Ferry Building", "display_name": "Ferry Building, 1 Ferry Plaza, San Francisco", "lat": "37.7955", "lon": "-122.3937"},
        {"name": "", "display_name": "Ferry Building Marketplace, San Francisco", "lat": "37.7956", "lon": "-122.3935"},
    ]
    results = client.get("/api/places/search", params={"q": "ferry building"}).json()
    assert results == [
        {"name": "Ferry Building", "address": "Ferry Building, 1 Ferry Plaza, San Francisco", "lat": 37.7955, "lng": -122.3937},
        {"name": "Ferry Building Marketplace", "address": "Ferry Building Marketplace, San Francisco", "lat": 37.7956, "lng": -122.3935},
    ]
    request = fake_geocoder.calls[0]
    assert request.get_header("User-agent").startswith("TracepAI") and "q=ferry+building" in request.full_url
    assert client.get("/api/places/search", params={"q": "  "}).json() == []


def test_place_reverse_and_errors(client, fake_geocoder):
    fake_geocoder.reply = {"name": "Blue Bottle", "display_name": "Blue Bottle, Mint St, San Francisco", "lat": "37.78", "lon": "-122.40"}
    assert client.get("/api/places/reverse", params={"lat": 37.78, "lng": -122.4}).json()["name"] == "Blue Bottle"
    fake_geocoder.reply = {"error": "Unable to geocode"}
    assert client.get("/api/places/reverse", params={"lat": 0, "lng": 0}).json()["name"] == ""
    fake_geocoder.error = urllib.error.URLError("offline")
    res = client.get("/api/places/search", params={"q": "x"})
    assert res.status_code == 503 and "unavailable" in res.json()["detail"]


def jpeg_with_gps(lat: float, lng: float) -> bytes:
    def dms(value):
        value = abs(value)
        d = int(value)
        m = int((value - d) * 60)
        s = (value - d - m / 60) * 3600
        return (IFDRational(d, 1), IFDRational(m, 1), IFDRational(round(s * 10000), 10000))

    image = Image.new("RGB", (40, 40), "white")
    exif = image.getexif()
    exif.get_ifd(0x8825).update({1: "N" if lat >= 0 else "S", 2: dms(lat), 3: "E" if lng >= 0 else "W", 4: dms(lng)})
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_gps_from_photo():
    lat, lng = documents.gps_from_image(jpeg_with_gps(37.795512, -122.393701))
    assert abs(lat - 37.795512) < 1e-5 and abs(lng + 122.393701) < 1e-5
    lat, lng = documents.gps_from_image(jpeg_with_gps(-33.8568, 151.2153))
    assert lat < 0 and lng > 0
    assert documents.gps_from_image(fixtures.receipt()) is None
    assert documents.gps_from_image(b"not an image") is None


def test_scan_returns_photo_position(client, monkeypatch):
    from app import vision

    monkeypatch.setattr(vision, "_chat", lambda body: {"message": {"content": json.dumps(
        {"document_type": "receipt", "transactions": [{"date": "2026-09-21", "merchant": "Cafe", "amount": 4, "direction": "money_out"}]})}})
    scan = client.post("/api/receipts/scan", files={"file": ("p.jpg", jpeg_with_gps(37.7955, -122.3937), "image/jpeg")}).json()
    assert abs(scan["lat"] - 37.7955) < 1e-5 and abs(scan["lng"] + 122.3937) < 1e-5


def test_transaction_location(client):
    body = {"date": TODAY.isoformat(), "amount": 12, "merchant": "Ferry cafe", "wallet_id": wallet(client, "Cash"),
            "place": "Ferry Building", "lat": 37.7955, "lng": -122.3937}
    txn = client.post("/api/transactions", json=body).json()
    assert (txn["place"], txn["lat"], txn["lng"]) == ("Ferry Building", 37.7955, -122.3937)
    listed = next(t for t in client.get("/api/transactions", params={"q": "Ferry cafe"}).json())
    assert (listed["place"], listed["lat"], listed["lng"]) == ("Ferry Building", 37.7955, -122.3937)
    cleared = client.put(f"/api/transactions/{txn['id']}", json={**body, "place": None, "lat": None, "lng": None}).json()
    assert (cleared["place"], cleared["lat"], cleared["lng"]) == (None, None, None)
    assert client.post("/api/transactions", json={**body, "lat": 91}).status_code == 422
    assert client.post("/api/transactions", json={**body, "lng": -181}).status_code == 422
    client.delete(f"/api/transactions/{txn['id']}")


def test_seeded_locations(client):
    located = [t for t in client.get("/api/transactions").json() if t["lat"] is not None]
    assert len(located) > 20 and all(37.6 < t["lat"] < 37.9 and t["place"] for t in located)
    assert not any(t["lat"] is not None for t in client.get("/api/transactions", params={"q": "Netflix"}).json())


# Monthly summary


def test_summary_matches_transactions(client):
    month = (TODAY.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")  # last month, complete
    start = dt.date.fromisoformat(f"{month}-01")
    end = TODAY.replace(day=1) - dt.timedelta(days=1)
    txns = client.get("/api/transactions", params={"start": start.isoformat(), "end": end.isoformat()}).json()
    expenses = [t for t in txns if t["kind"] == "expense"]
    s = client.get("/api/analytics/summary", params={"month": month}).json()

    assert s["in_progress"] is False and s["compared_days"] == end.day
    assert s["expenses"] == round(sum(t["amount"] for t in expenses), 2)
    assert s["income"] == round(sum(t["amount"] for t in txns if t["kind"] == "income"), 2)
    assert s["net"] == round(s["income"] - s["expenses"], 2)
    assert s["biggest"]["amount"] == max(t["amount"] for t in expenses)
    cats = client.get("/api/analytics/categories", params={"start": start.isoformat(), "end": end.isoformat()}).json()
    assert s["top_category"]["name"] == cats[0]["name"] and s["top_category"]["total"] == cats[0]["total"]
    budgets = client.get("/api/analytics/budgets", params={"month": month}).json()
    assert s["over_budget"] == [b["name"] for b in budgets if b["percent"] >= 100]


def test_summary_current_month_compares_same_days(client):
    s = client.get("/api/analytics/summary").json()
    assert s["in_progress"] is True and s["compared_days"] == TODAY.day
    prev_start = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    prev_end = prev_start.replace(day=min(TODAY.day, (TODAY.replace(day=1) - dt.timedelta(days=1)).day))
    prev = client.get("/api/transactions", params={"start": prev_start.isoformat(), "end": prev_end.isoformat()}).json()
    prev_spent = sum(t["amount"] for t in prev if t["kind"] == "expense")
    now = client.get("/api/transactions", params={"start": TODAY.replace(day=1).isoformat(), "end": TODAY.isoformat()}).json()
    now_spent = sum(t["amount"] for t in now if t["kind"] == "expense")
    assert s["change"] == round(now_spent - prev_spent, 2)
    assert s["change_percent"] == round(100 * (now_spent - prev_spent) / prev_spent, 1)


def test_summary_empty_month(client):
    s = client.get("/api/analytics/summary", params={"month": "2001-01"}).json()
    assert (s["income"], s["expenses"], s["savings_rate"], s["top_category"], s["biggest"], s["most_visited"], s["change_percent"]) == (
        0, 0, None, None, None, None, None)


# Undo


def test_undo_by_reposting(client):
    split = next(t for t in client.get("/api/transactions").json() if t["splits"])
    client.delete(f"/api/transactions/{split['id']}")
    body = {k: v for k, v in split.items() if k not in ("id", "recurring_id")}
    restored = client.post("/api/transactions", json=body).json()
    assert {k: v for k, v in restored.items() if k not in ("id",)} == {**body, "recurring_id": None}


# Adding columns to an existing database


def test_add_missing_columns(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE "transaction" (id INTEGER PRIMARY KEY, user_id INTEGER, wallet_id INTEGER, amount FLOAT, '
                'kind VARCHAR, merchant VARCHAR, date DATE, notes VARCHAR, tags VARCHAR)')
    con.execute("""INSERT INTO "transaction" VALUES (1, 1, 1, 9.5, 'expense', 'Old shop', '2026-01-02', '', '')""")
    con.commit()
    con.close()

    engine = app_db.create_engine(f"sqlite:///{path}")
    monkeypatch.setattr(app_db, "engine", engine)
    app_db.add_missing_columns()
    con = sqlite3.connect(path)
    columns = {row[1] for row in con.execute('PRAGMA table_info("transaction")')}
    assert {"place", "lat", "lng", "receipt_path", "to_wallet_id", "goal_id"} <= columns
    assert con.execute('SELECT merchant, amount, place FROM "transaction"').fetchall() == [("Old shop", 9.5, None)]
    app_db.add_missing_columns()  # running again changes nothing
    con.close()
