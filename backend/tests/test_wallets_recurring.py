import datetime as dt

from sqlmodel import Session, select

from app.db import engine
from app.models import Frequency, RecurringRule, Transaction
from app.recurring import advance, post_due

TODAY = dt.date.today()


def wallets(client):
    return {w["name"]: w for w in client.get("/api/wallets").json()}


def test_wallet_balances_match_transactions(client):
    ws = wallets(client)
    for w in ws.values():
        total = w["opening_balance"]
        for t in client.get("/api/transactions", params={"wallet": w["id"]}).json():
            if t["kind"] == "transfer":
                total += t["amount"] if t["to_wallet_id"] == w["id"] else -t["amount"]
            else:
                total += t["amount"] if t["kind"] == "income" else -t["amount"]
        assert round(total, 2) == w["balance"]
    all_balance = client.get("/api/analytics/balance").json()[-1]["balance"]
    assert round(sum(w["balance"] for w in ws.values()), 2) == all_balance
    assert client.get("/api/analytics/balance", params={"wallet": ws["Savings"]["id"]}).json()[-1]["balance"] == ws["Savings"]["balance"]


def test_transfer_moves_money_but_not_totals(client):
    ws = wallets(client)
    params = {"start": TODAY.isoformat(), "end": TODAY.isoformat()}
    before = client.get("/api/analytics/cashflow", params=params).json()
    body = {"date": TODAY.isoformat(), "amount": 75, "kind": "transfer", "wallet_id": ws["Checking"]["id"], "to_wallet_id": ws["Cash"]["id"]}
    txn = client.post("/api/transactions", json=body).json()
    after = wallets(client)
    assert after["Checking"]["balance"] == round(ws["Checking"]["balance"] - 75, 2)
    assert after["Cash"]["balance"] == round(ws["Cash"]["balance"] + 75, 2)
    assert client.get("/api/analytics/cashflow", params=params).json() == before
    client.delete(f"/api/transactions/{txn['id']}")


def test_invalid_transfers(client):
    ws = wallets(client)
    base = {"date": TODAY.isoformat(), "amount": 10, "kind": "transfer", "wallet_id": ws["Checking"]["id"]}
    assert client.post("/api/transactions", json=base).status_code == 422
    assert client.post("/api/transactions", json={**base, "to_wallet_id": ws["Checking"]["id"]}).status_code == 422
    cats = client.get("/api/categories").json()
    assert client.post("/api/transactions", json={**base, "to_wallet_id": ws["Cash"]["id"], "category_id": cats[0]["id"]}).status_code == 422


def test_wallet_delete_rules(client):
    ws = wallets(client)
    assert client.delete(f"/api/wallets/{ws['Checking']['id']}").status_code == 409
    new = client.post("/api/wallets", json={"name": "Travel", "kind": "cash", "color_slot": 5}).json()
    assert client.delete(f"/api/wallets/{new['id']}").status_code == 200


def test_advance():
    assert advance(dt.date(2026, 1, 31), Frequency.monthly) == dt.date(2026, 2, 28)
    assert advance(dt.date(2026, 12, 15), Frequency.monthly) == dt.date(2027, 1, 15)
    assert advance(dt.date(2028, 2, 29), Frequency.yearly) == dt.date(2029, 2, 28)
    assert advance(dt.date(2026, 9, 1), Frequency.weekly) == dt.date(2026, 9, 8)


def test_seeded_rules_posted_every_month(client):
    rules = {r["merchant"]: r for r in client.get("/api/recurring").json()}
    assert rules["Acme Corp"]["next_date"] > TODAY.isoformat()
    salaries = client.get("/api/transactions", params={"q": "Acme Corp"}).json()
    assert len(salaries) == 6
    assert all(t["recurring_id"] == rules["Acme Corp"]["id"] for t in salaries)


def test_post_due_catches_up(client):
    with Session(engine) as db:
        user_id = db.exec(select(Transaction)).first().user_id
        wallet_id = db.exec(select(Transaction)).first().wallet_id
        rule = RecurringRule(user_id=user_id, wallet_id=wallet_id, amount=9, merchant="Gym", frequency=Frequency.weekly,
                             next_date=TODAY - dt.timedelta(days=20))
        db.add(rule)
        db.commit()
        post_due(db, user_id, TODAY)
        posted = db.exec(select(Transaction).where(Transaction.recurring_id == rule.id)).all()
        assert len(posted) == 3
        assert rule.next_date > TODAY
        for t in posted:
            db.delete(t)
        db.delete(rule)
        db.commit()


def test_repeat_creates_rule(client):
    ws = wallets(client)
    body = {"date": TODAY.isoformat(), "amount": 40, "merchant": "Yoga Studio", "wallet_id": ws["Credit card"]["id"], "repeat": "monthly"}
    txn = client.post("/api/transactions", json=body).json()
    rule = next(r for r in client.get("/api/recurring").json() if r["merchant"] == "Yoga Studio")
    assert txn["recurring_id"] == rule["id"]
    assert rule["next_date"] == advance(TODAY, Frequency.monthly).isoformat()
    upcoming = client.get("/api/recurring/upcoming", params={"days": 40}).json()
    assert any(u["merchant"] == "Yoga Studio" for u in upcoming)
    client.delete(f"/api/recurring/{rule['id']}")
    client.delete(f"/api/transactions/{txn['id']}")


def test_suggestions_find_subscriptions(client):
    found = {s["merchant"]: s for s in client.get("/api/recurring/suggestions").json()}
    assert {"Netflix", "Spotify", "iCloud"} <= set(found)
    assert found["Netflix"]["amount"] == 15.49
    assert found["Netflix"]["frequency"] == "monthly"
    assert "Acme Corp" not in found
    rule = client.post("/api/recurring", json={k: found["Netflix"][k] for k in ("merchant", "amount", "kind", "wallet_id", "category_id", "frequency", "next_date")}).json()
    assert "Netflix" not in {s["merchant"] for s in client.get("/api/recurring/suggestions").json()}
    client.delete(f"/api/recurring/{rule['id']}")


def test_post_due_is_safe_under_concurrent_requests(client):
    from concurrent.futures import ThreadPoolExecutor

    with Session(engine) as db:
        first = db.exec(select(Transaction)).first()
        rule = RecurringRule(user_id=first.user_id, wallet_id=first.wallet_id, amount=5, merchant="Race", next_date=TODAY)
        db.add(rule)
        db.commit()
        rule_id, user_id = rule.id, first.user_id

    def run(_):
        with Session(engine) as db:
            post_due(db, user_id, TODAY)

    for _ in range(3):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(run, range(8)))

    with Session(engine) as db:
        posted = db.exec(select(Transaction).where(Transaction.recurring_id == rule_id)).all()
        assert len(posted) == 1
        for t in posted:
            db.delete(t)
        db.delete(db.get(RecurringRule, rule_id))
        db.commit()
