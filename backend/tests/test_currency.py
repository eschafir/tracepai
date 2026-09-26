import datetime as dt
import sqlite3

import pytest
from sqlmodel import select

from app import db as app_db
from app import fx
from app.models import FxRate

DAY = dt.date(2015, 6, 10)  # far from the seeded months, so other tests' totals don't change
TODAY = dt.date.today()


def wallets(client):
    return {w["name"]: w for w in client.get("/api/wallets").json()}


@pytest.fixture
def fake_rates(monkeypatch):
    """1 USD = 0.5 EUR = 2 GBP, from 2011 on. Resets the once-a-day check around the test."""
    fx._checked.clear()
    rates = {"EUR": 0.5, "GBP": 2.0}
    monkeypatch.setattr(fx, "fetch", lambda currency: [(dt.date(2011, 1, 1), rates[currency])] if currency in rates else [])
    yield
    fx._checked.clear()


# Sources and lookups


def test_fetch_parses_each_source(monkeypatch):
    responses = {
        "argentinadatos": [{"casa": "oficial", "compra": 1490, "venta": 1540, "fecha": "2026-09-25"}],
        "frankfurter": {"rates": {"2026-09-24": {"EUR": 0.86}, "2026-09-25": {"EUR": 0.85}}},
        "er-api": {"rates": {"CLP": 962.5}},
    }
    urls = []

    def fake(url):
        urls.append(url)
        return next(v for k, v in responses.items() if k in url)

    monkeypatch.setattr(fx, "get_json", fake)
    assert fx.fetch("ARS") == [(dt.date(2026, 9, 25), 1540.0)]
    assert fx.fetch("EUR") == [(dt.date(2026, 9, 24), 0.86), (dt.date(2026, 9, 25), 0.85)]
    assert "symbols=EUR" in urls[1] and "base=USD" in urls[1]
    assert fx.fetch("CLP") == [(TODAY, 962.5)]
    assert fx.fetch("XXX") == []


def test_nearest_earlier_rate():
    rates = fx.Rates.__new__(fx.Rates)
    rates.table = {"EUR": ([dt.date(2026, 1, 2), dt.date(2026, 1, 5)], [0.8, 0.9])}
    assert rates.per_usd("EUR", dt.date(2026, 1, 4)) == 0.8  # a weekend uses Friday's rate
    assert rates.per_usd("EUR", dt.date(2026, 1, 5)) == 0.9
    assert rates.per_usd("EUR", dt.date(2025, 12, 1)) == 0.8  # before the first rate: the earliest one
    assert rates.usd(9, "EUR", dt.date(2026, 2, 1)) == 10
    assert rates.usd(7, "USD") == 7


def test_refresh_once_a_day_and_failures_keep_rates(monkeypatch):
    fx._checked.clear()
    calls = []
    monkeypatch.setattr(fx, "fetch", lambda c: calls.append(c) or [(dt.date(2020, 1, 1), 3.0)])
    with app_db.Session(app_db.engine) as db:
        fx.refresh(db, "ZZA")
        fx.refresh(db, "ZZA")
        assert calls == ["ZZA"]

        fx._checked.clear()
        monkeypatch.setattr(fx, "fetch", lambda c: (_ for _ in ()).throw(OSError("offline")))
        fx.refresh(db, "ZZA", strict=True)  # stored rates are still there
        assert db.exec(select(FxRate).where(FxRate.currency == "ZZA")).one().per_usd == 3.0
        with pytest.raises(ValueError, match="No exchange rate"):
            fx.refresh(db, "ZZB", strict=True)
    fx._checked.clear()


# Wallets in other currencies


def test_foreign_wallet_in_analytics(client, fake_rates):
    assert client.post("/api/wallets", json={"name": "Bad", "color_slot": 1, "currency": "XYZ"}).status_code == 422
    euro = client.post("/api/wallets", json={"name": "Euro card", "kind": "card", "color_slot": 2, "currency": "eur"}).json()
    assert euro["currency"] == "EUR"
    category = client.post("/api/categories", json={"name": "Travel FX", "color_slot": 3}).json()
    budget = client.post("/api/budgets", json={"category_id": category["id"], "monthly_limit": 100}).json()
    txn = client.post("/api/transactions", json={"date": DAY.isoformat(), "amount": 10, "kind": "expense", "merchant": "Paris cafe",
                                                 "wallet_id": euro["id"], "category_id": category["id"]}).json()

    cats = client.get("/api/analytics/categories", params={"start": DAY.isoformat(), "end": DAY.isoformat()}).json()
    assert next(c["total"] for c in cats if c["name"] == "Travel FX") == 20  # 10 EUR at 0.5 EUR per USD
    summary = client.get("/api/analytics/summary", params={"month": "2015-06"}).json()
    assert summary["expenses"] == 20 and summary["biggest"]["amount"] == 20
    budgets = client.get("/api/analytics/budgets", params={"month": "2015-06"}).json()
    assert next(b["spent"] for b in budgets if b["category_id"] == category["id"]) == 20
    w = wallets(client)["Euro card"]
    assert (w["balance"], w["balance_usd"], w["in_use"]) == (-10, -20, True)

    client.delete(f"/api/transactions/{txn['id']}")
    client.delete(f"/api/budgets/{budget['id']}")
    client.delete(f"/api/categories/{category['id']}")
    client.delete(f"/api/wallets/{euro['id']}")


def test_transfers_between_currencies(client, fake_rates):
    checking = wallets(client)["Checking"]["id"]
    euro = client.post("/api/wallets", json={"name": "Euro savings", "kind": "savings", "color_slot": 2, "currency": "EUR"}).json()
    body = {"date": DAY.isoformat(), "amount": 50, "kind": "transfer", "wallet_id": checking, "to_wallet_id": euro["id"]}
    missing = client.post("/api/transactions", json=body)
    assert missing.status_code == 422 and "EUR" in missing.json()["detail"]
    before = wallets(client)["Checking"]["balance"]
    txn = client.post("/api/transactions", json={**body, "to_amount": 24}).json()
    after = wallets(client)
    assert after["Euro savings"]["balance"] == 24 and after["Checking"]["balance"] == round(before - 50, 2)
    same = {**body, "to_wallet_id": wallets(client)["Cash"]["id"], "to_amount": 5}
    assert client.post("/api/transactions", json=same).status_code == 422
    assert client.post("/api/transactions", json={**body, "kind": "expense", "to_wallet_id": None, "to_amount": 5}).status_code == 422

    # A recurring transfer carries the received amount into each posted transaction.
    rule = client.post("/api/recurring", json={**{k: v for k, v in body.items() if k != "date"}, "to_amount": 24,
                                               "merchant": "FX monthly", "frequency": "monthly", "next_date": TODAY.isoformat()}).json()
    assert client.post("/api/recurring", json={**rule, "to_amount": None}).status_code == 422
    posted = [t for t in client.get("/api/transactions", params={"q": "FX monthly"}).json()]
    assert [t["to_amount"] for t in posted] == [24]

    # The currency is locked once the wallet has transactions; an unused wallet can change.
    edit = {k: euro[k] for k in ("name", "kind", "color_slot", "opening_balance")}
    assert client.put(f"/api/wallets/{euro['id']}", json={**edit, "currency": "GBP"}).status_code == 409
    empty = client.post("/api/wallets", json={**edit, "name": "Spare", "currency": "EUR"}).json()
    assert client.put(f"/api/wallets/{empty['id']}", json={**edit, "name": "Spare", "currency": "GBP"}).json()["currency"] == "GBP"

    for t in posted + [txn]:
        client.delete(f"/api/transactions/{t['id']}")
    client.delete(f"/api/recurring/{rule['id']}")
    client.delete(f"/api/wallets/{euro['id']}")
    client.delete(f"/api/wallets/{empty['id']}")


def test_goal_in_another_currency(client, fake_rates):
    checking = wallets(client)["Checking"]["id"]
    euro = client.post("/api/wallets", json={"name": "Euro goal", "kind": "savings", "color_slot": 2, "currency": "EUR"}).json()
    goal = client.post("/api/goals", json={"name": "Paris", "target_amount": 1000, "wallet_id": euro["id"]}).json()
    url = f"/api/goals/{goal['id']}/contributions"
    add = {"date": DAY.isoformat(), "amount": 100, "direction": "in", "wallet_id": checking}
    assert client.post(url, json=add).status_code == 422
    assert client.post(url, json={**add, "received": 48}).json()["saved"] == 48
    assert client.post(url, json={**add, "direction": "out", "amount": 8, "received": 16}).json()["saved"] == 40
    assert client.get("/api/fx/convert", params={"amount": 100, "source": "USD", "to": "EUR"}).json() == {"amount": 50}
    for c in client.get(url).json():
        client.delete(f"/api/goals/contributions/{c['id']}")
    client.delete(f"/api/goals/{goal['id']}")
    client.delete(f"/api/wallets/{euro['id']}")


def test_networth(client):
    points = client.get("/api/analytics/networth").json()
    assert points[-1]["date"] == TODAY.isoformat() and len(points) >= 2
    assert all(p["net"] == round(p["assets"] + p["debts"], 2) for p in points)
    total = sum(w["balance_usd"] for w in client.get("/api/wallets").json())
    assert points[-1]["net"] == pytest.approx(total, abs=0.05)
    assert any(p["debts"] < 0 for p in points)  # the seeded credit card
    assert client.get("/api/analytics/balance").json()[-1]["balance"] == pytest.approx(total, abs=0.05)


def test_old_wallets_become_usd(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE wallet (id INTEGER PRIMARY KEY, user_id INTEGER, name VARCHAR, kind VARCHAR, color_slot INTEGER, opening_balance FLOAT)")
    con.execute("INSERT INTO wallet VALUES (1, 1, 'Checking', 'bank', 1, 100)")
    con.commit()
    con.close()
    monkeypatch.setattr(app_db, "engine", app_db.create_engine(f"sqlite:///{path}"))
    app_db.add_missing_columns()
    con = sqlite3.connect(path)
    assert con.execute("SELECT name, currency FROM wallet").fetchall() == [("Checking", "USD")]
    con.close()


def test_currency_list(client, monkeypatch):
    monkeypatch.setattr(fx, "get_json", lambda url: {"rates": {"USD": 1, "CLP": 962.5, "UYU": 40.1}})
    codes = client.get("/api/fx/currencies").json()
    assert {"USD", "ARS", "EUR", "CLP", "UYU"} <= set(codes) and codes == sorted(codes)
    monkeypatch.setattr(fx, "get_json", lambda url: (_ for _ in ()).throw(OSError("offline")))
    assert {"USD", "ARS", "EUR"} <= set(client.get("/api/fx/currencies").json())
