import datetime as dt

from fastapi.testclient import TestClient

from app.main import app

TODAY = dt.date.today()
MONTH_START = TODAY.replace(day=1).isoformat()


def test_auth_required_and_bad_login(client):
    with TestClient(app) as anon:
        assert anon.get("/api/transactions").status_code == 401
        assert anon.post("/api/auth/login", json={"username": "user", "password": "nope"}).status_code == 401


def test_me(client):
    assert client.get("/api/auth/me").json() == {"username": "user"}


def wallet_id(client, name="Checking"):
    return next(w["id"] for w in client.get("/api/wallets").json() if w["name"] == name)


def test_seeded_data(client):
    assert len(client.get("/api/categories").json()) == 10
    assert [w["name"] for w in client.get("/api/wallets").json()] == ["Checking", "Credit card", "Cash", "Savings"]
    assert len(client.get("/api/budgets").json()) == 8
    txns = client.get("/api/transactions").json()
    assert len(txns) > 100
    assert any(t["splits"] for t in txns)


def test_transaction_crud_with_splits(client):
    cats = {c["name"]: c["id"] for c in client.get("/api/categories").json()}
    body = {
        "date": TODAY.isoformat(),
        "amount": 150,
        "merchant": "Test Mart",
        "category_id": cats["Groceries"],
        "tags": "test",
        "wallet_id": wallet_id(client),
    }
    created = client.post("/api/transactions", json=body).json()
    assert created["category_id"] == cats["Groceries"]

    body["splits"] = [{"category_id": cats["Groceries"], "amount": 100}, {"category_id": cats["Household"], "amount": 50}]
    updated = client.put(f"/api/transactions/{created['id']}", json=body).json()
    assert updated["category_id"] is None
    assert len(updated["splits"]) == 2

    assert [t["id"] for t in client.get("/api/transactions", params={"q": "test mart"}).json()] == [created["id"]]
    assert created["id"] in [t["id"] for t in client.get("/api/transactions", params={"category": cats["Household"]}).json()]

    assert client.delete(f"/api/transactions/{created['id']}").status_code == 200
    assert client.get("/api/transactions", params={"q": "test mart"}).json() == []


def test_invalid_transaction(client):
    assert client.post("/api/transactions", json={"date": TODAY.isoformat(), "amount": -5, "wallet_id": wallet_id(client)}).status_code == 422


def test_category_and_budget_crud(client):
    cat = client.post("/api/categories", json={"name": "Pets", "color_slot": 3}).json()
    budget = client.post("/api/budgets", json={"category_id": cat["id"], "monthly_limit": 50}).json()
    assert client.put(f"/api/budgets/{budget['id']}", json={"category_id": cat["id"], "monthly_limit": 80}).json()["monthly_limit"] == 80
    assert client.delete(f"/api/budgets/{budget['id']}").status_code == 200
    assert client.delete(f"/api/categories/{cat['id']}").status_code == 200
    assert client.post("/api/categories", json={"name": "Bad", "color_slot": 9}).status_code == 422


def test_analytics(client):
    params = {"start": MONTH_START, "end": TODAY.isoformat()}
    cats = client.get("/api/analytics/categories", params=params).json()
    assert cats[0]["name"] == "Rent" and cats[0]["total"] == 1450

    flow = client.get("/api/analytics/cashflow", params=params).json()
    assert len(flow) == TODAY.day
    assert flow[0]["income"] >= 5200

    budgets = client.get("/api/analytics/budgets").json()
    assert {b["name"] for b in budgets} >= {"Rent", "Dining"}
    assert next(b for b in budgets if b["name"] == "Rent")["percent"] == round(100 * 1450 / 1500, 1)

    merchants = client.get("/api/analytics/merchants", params={"start": "2000-01-01", "end": TODAY.isoformat()}).json()
    assert merchants["largest"][0]["merchant"] == "United Airlines"
    assert merchants["frequent"][0]["count"] >= merchants["frequent"][-1]["count"]

    comparison = client.get("/api/analytics/comparison").json()
    assert comparison[TODAY.day - 1]["current"] is not None
    if TODAY.day < len(comparison):
        assert comparison[TODAY.day]["current"] is None

    balance = client.get("/api/analytics/balance").json()
    assert balance[0]["balance"] > 0


def test_export(client):
    csv = client.get("/api/export", params={"format": "csv"})
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.startswith("id,date,kind,amount,merchant,category,wallet,to_wallet")
    assert "Groceries: 100.0; Household: 50.0" in csv.text
    assert isinstance(client.get("/api/export", params={"format": "json"}).json(), list)
