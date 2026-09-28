"""Access checks, profile import validation and data integrity (the high and medium items in docs/code_review.md)."""

import datetime as dt
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app import db as app_db
from app import fx, ocr
from app.main import app
from app.models import Session as UserSession
from app.models import User

DAY = "2014-02-10"  # a month no other test uses
pytestmark = pytest.mark.usefixtures("client")  # starts the app, which creates the database


def signup(username: str) -> TestClient:
    person = TestClient(app, raise_server_exceptions=False)
    assert person.post("/api/auth/signup", json={"username": username, "password": "secret-pass"}).status_code == 200
    return person


def cash(person: TestClient) -> int:
    return next(w["id"] for w in person.get("/api/wallets").json() if w["name"] == "Cash")


def category(person: TestClient, name: str = "Groceries") -> int:
    return next(c["id"] for c in person.get("/api/categories").json() if c["name"] == name)


def expense(wallet_id: int, **extra) -> dict:
    return {"date": DAY, "amount": 5, "kind": "expense", "merchant": "Shop", "wallet_id": wallet_id, **extra}


def upload(person: TestClient, profile: dict, mode: str = "merge"):
    return person.post("/api/import/profile", files={"file": ("p.json", json.dumps(profile).encode(), "application/json")}, data={"mode": mode})


def gif_with_html() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, format="GIF")
    return out.getvalue() + b"<script>alert(1)</script>"


def test_receipts_are_named_by_content_and_private(monkeypatch):
    monkeypatch.setattr(ocr, "read_text", lambda pages: "")
    owner, other = signup("rita"), signup("rex")
    scan = owner.post("/api/receipts/scan", files={"file": ("x.html", gif_with_html(), "text/html")}).json()
    name = scan["receipt_path"]
    assert name.endswith(".gif") and name.startswith(f"{owner.get('/api/auth/me').json()['id']}-")
    served = owner.get(f"/api/receipts/{name}")
    assert served.headers["content-type"] == "image/gif" and served.headers["x-content-type-options"] == "nosniff"
    assert other.get(f"/api/receipts/{name}").status_code == 404
    # someone else's receipt can't be attached to get access to it
    assert other.post("/api/transactions", json=expense(cash(other), receipt_path=name)).status_code == 422
    assert owner.post("/api/transactions", json=expense(cash(owner), receipt_path=name)).status_code == 200


def test_references_must_be_your_own():
    owner, other = signup("olga"), signup("otto")
    wallet, groceries = cash(owner), category(owner)
    mine = cash(other)
    assert other.post("/api/transactions", json=expense(wallet)).status_code == 422
    assert other.post("/api/transactions", json=expense(mine, category_id=groceries)).status_code == 422
    split = [{"category_id": groceries, "amount": 5}]
    assert other.post("/api/transactions", json=expense(mine, splits=split)).status_code == 422
    assert other.post("/api/transactions", json=expense(999999)).status_code == 422  # a wallet that doesn't exist
    transfer = {"date": DAY, "amount": 5, "kind": "transfer", "wallet_id": mine, "to_wallet_id": wallet}
    assert other.post("/api/transactions", json=transfer).status_code == 422
    rule = {"amount": 5, "merchant": "Gym", "wallet_id": wallet, "next_date": "2099-01-01"}
    assert other.post("/api/recurring", json=rule).status_code == 422
    assert other.post("/api/budgets", json={"category_id": groceries, "monthly_limit": 10}).status_code == 422
    assert other.post("/api/goals", json={"name": "Car", "target_amount": 10, "wallet_id": wallet}).status_code == 422
    assert other.get("/api/transactions").json() == []


def test_shared_wallet_expenses_use_the_owners_categories():
    owner, member = signup("sasha"), signup("sam")
    ledger = owner.post("/api/shared", json={"name": "Flat", "currency": "USD", "members": ["sam"]}).json()
    member.post(f"/api/shared/{ledger['id']}/accept")
    body = expense(cash(member), shared_wallet_id=ledger["id"])
    assert member.post("/api/transactions", json={**body, "category_id": category(member)}).status_code == 422
    txn = member.post("/api/transactions", json={**body, "category_id": category(owner)}).json()
    member.delete(f"/api/transactions/{txn['id']}")
    owner.delete(f"/api/shared/{ledger['id']}")


def test_profile_import_rejects_bad_records_and_saves_nothing():
    person = signup("paula")
    before = person.get("/api/wallets").json()
    bad = {"wallets": [{"id": 1, "name": "W", "color_slot": 1}], "categories": [], "transactions": [{"wallet_id": 1, "amount": 5, "kind": "bogus", "date": DAY}]}
    response = upload(person, bad)
    assert response.status_code == 400 and "Transaction 1" in response.json()["detail"]
    missing = {"wallets": [{"id": 1, "name": "W", "color_slot": 1}], "categories": [], "transactions": [{"wallet_id": 2, "amount": 5, "date": DAY}]}
    assert "wallet that isn't in the file" in upload(person, missing).json()["detail"]
    assert upload(person, {"wallets": [{"name": "W", "color_slot": 99}], "categories": []}).status_code == 400
    assert person.get("/api/wallets").json() == before
    assert person.get("/api/transactions").status_code == 200


def test_profile_merge_twice_adds_nothing_new():
    person = signup("mia")
    person.post("/api/transactions", json=expense(cash(person), category_id=category(person)))
    person.post("/api/recurring", json={"amount": 9, "merchant": "Gym", "wallet_id": cash(person), "next_date": "2099-01-01"})
    person.post("/api/goals", json={"name": "Bike", "target_amount": 100, "wallet_id": cash(person)})
    profile = person.get("/api/export/profile").json()
    counts = [len(person.get(path).json()) for path in ("/api/transactions", "/api/recurring", "/api/goals", "/api/wallets")]
    added = upload(person, profile).json()["imported"]
    assert added == {"wallets": 0, "categories": 0, "budgets": 0, "goals": 0, "recurring_rules": 0, "transactions": 0}
    assert [len(person.get(path).json()) for path in ("/api/transactions", "/api/recurring", "/api/goals", "/api/wallets")] == counts


def test_replace_keeps_settle_up_payments_out_of_spending():
    owner, member = signup("nora"), signup("ned")
    ledger = owner.post("/api/shared", json={"name": "Trip", "currency": "USD", "members": ["ned"]}).json()
    member.post(f"/api/shared/{ledger['id']}/accept")
    ned_id, nora_id = member.get("/api/auth/me").json()["id"], owner.get("/api/auth/me").json()["id"]
    url = f"/api/shared/{ledger['id']}/settlements"
    member.post(url, json={"from_user_id": ned_id, "to_user_id": nora_id, "amount": 10, "date": DAY, "wallet_id": cash(member)})
    assert upload(member, member.get("/api/export/profile").json(), mode="replace").status_code == 409  # still in a shared wallet
    owner.post(url, json={"from_user_id": nora_id, "to_user_id": ned_id, "amount": 10, "date": DAY})
    assert member.delete(f"/api/shared/{ledger['id']}/members/{ned_id}").status_code == 200

    assert upload(member, member.get("/api/export/profile").json(), mode="replace").status_code == 200
    [payment] = member.get("/api/transactions").json()
    assert payment["settlement_id"] is not None
    assert member.get("/api/analytics/summary", params={"month": DAY[:7]}).json()["expenses"] == 0


def test_currency_is_stored_uppercase():
    person = signup("uma")
    wallet = person.get("/api/wallets").json()[0]
    person.post("/api/transactions", json=expense(wallet["id"]))
    fields = {k: wallet[k] for k in ("name", "kind", "color_slot", "opening_balance")}
    assert person.put(f"/api/wallets/{wallet['id']}", json={**fields, "currency": "usd"}).json()["currency"] == "USD"
    assert person.get("/api/wallets").status_code == 200
    assert person.get("/api/analytics/summary", params={"month": DAY[:7]}).status_code == 200


def test_wallets_and_categories_in_use_cant_be_deleted():
    person = signup("walt")
    wallet = person.post("/api/wallets", json={"name": "Bank", "kind": "bank", "color_slot": 1}).json()
    rule = person.post("/api/recurring", json={"amount": 9, "merchant": "Gym", "wallet_id": wallet["id"], "next_date": "2099-01-01"}).json()
    assert person.delete(f"/api/wallets/{wallet['id']}").status_code == 409
    person.delete(f"/api/recurring/{rule['id']}")
    goal = person.post("/api/goals", json={"name": "Boat", "target_amount": 10, "wallet_id": wallet["id"]}).json()
    assert person.delete(f"/api/wallets/{wallet['id']}").status_code == 409
    person.delete(f"/api/goals/{goal['id']}")
    assert person.delete(f"/api/wallets/{wallet['id']}").status_code == 200

    used, unused = category(person, "Groceries"), category(person, "Dining")
    txn = person.post("/api/transactions", json=expense(cash(person), splits=[{"category_id": used, "amount": 5}])).json()
    assert person.delete(f"/api/categories/{used}").status_code == 409
    person.delete(f"/api/transactions/{txn['id']}")
    person.post("/api/budgets", json={"category_id": unused, "monthly_limit": 50})
    assert person.delete(f"/api/categories/{unused}").status_code == 200
    assert person.get("/api/budgets").json() == []


def test_posted_transactions_outlive_their_rule():
    person = signup("rory")
    start = (dt.date.today() - dt.timedelta(days=100)).isoformat()
    rule = person.post("/api/recurring", json={"amount": 9, "merchant": "Gym", "wallet_id": cash(person), "next_date": start}).json()
    assert len(person.get("/api/transactions").json()) > 1  # posted every month since start
    assert person.delete(f"/api/recurring/{rule['id']}").status_code == 200
    assert all(t["recurring_id"] is None for t in person.get("/api/transactions").json())


def test_sessions_expire_and_password_change_signs_out_other_devices():
    phone, laptop = signup("sid"), TestClient(app)
    token = laptop.post("/api/auth/login", json={"username": "sid", "password": "secret-pass"}).json()["token"]
    assert phone.put("/api/auth/profile", json={"current_password": "secret-pass", "password": "new-secret-pass"}).status_code == 200
    assert laptop.get("/api/auth/me").status_code == 401 and phone.get("/api/auth/me").status_code == 200
    with Session(app_db.engine) as db:
        assert db.get(UserSession, token) is None
        user_id = db.exec(select(User.id).where(User.username == "sid")).one()
        for session in db.exec(select(UserSession).where(UserSession.user_id == user_id)):
            session.created_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=31)
            db.add(session)
        db.commit()
    assert phone.get("/api/auth/me").status_code == 401


def test_repeated_failed_logins_are_blocked():
    signup("lena")
    guesser = TestClient(app)
    for _ in range(5):
        assert guesser.post("/api/auth/login", json={"username": "lena", "password": "wrong-guess"}).status_code == 401
    assert guesser.post("/api/auth/login", json={"username": "lena", "password": "secret-pass"}).status_code == 429


def test_uploads_have_a_size_limit():
    person = signup("zed")
    huge = b"date,amount\n" + b"0" * (15 * 1024 * 1024)
    assert person.post("/api/import/preview", files={"file": ("s.csv", huge, "text/csv")}).status_code == 413


def test_demo_account_is_only_seeded_when_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(app_db, "engine", app_db.create_engine(f"sqlite:///{tmp_path / 'fresh.db'}"))
    monkeypatch.setattr(app_db, "SEED_DEMO", False)
    app_db.init_db()
    with Session(app_db.engine) as db:
        assert db.exec(select(User)).first() is None


def test_failed_rate_fetch_waits_before_trying_again(monkeypatch):
    fx._checked.clear()
    calls = []
    monkeypatch.setattr(fx, "fetch", lambda c: calls.append(c) or (_ for _ in ()).throw(OSError("offline")))
    with Session(app_db.engine) as db:
        fx.refresh(db, "ZZC")
        fx.refresh(db, "ZZC")
        assert calls == ["ZZC"]
        with pytest.raises(Exception, match="No exchange rate is stored for ZZC"):
            fx.Rates(db, {"ZZC"}).per_usd("ZZC")
    fx._checked.clear()
    assert signup("fay").get("/api/fx/convert", params={"amount": 1, "to": "eur"}).status_code == 422


def test_failed_logins_from_one_client_dont_lock_out_others():
    signup("gina")
    attacker = TestClient(app, client=("203.0.113.9", 50000))
    for _ in range(5):
        attacker.post("/api/auth/login", json={"username": "gina", "password": "wrong-guess"})
    assert attacker.post("/api/auth/login", json={"username": "gina", "password": "secret-pass"}).status_code == 429
    owner = TestClient(app, client=("198.51.100.4", 50000))
    assert owner.post("/api/auth/login", json={"username": "gina", "password": "secret-pass"}).status_code == 200


def test_split_amounts_must_add_up_to_the_total():
    person = signup("sofia")
    groceries, household = category(person, "Groceries"), category(person, "Household")
    splits = [{"category_id": groceries, "amount": 3}, {"category_id": household, "amount": 2}]
    assert person.post("/api/transactions", json=expense(cash(person), splits=splits[:1])).status_code == 422
    assert person.post("/api/transactions", json=expense(cash(person), splits=splits)).status_code == 200


def test_profile_merge_refuses_a_wallet_in_another_currency(monkeypatch):
    monkeypatch.setattr(fx, "fetch", lambda currency: [(dt.date(2011, 1, 1), 0.5)] if currency == "EUR" else [])
    fx._checked.clear()
    person = signup("mara")
    profile = {"wallets": [{"id": 7, "name": "Cash", "color_slot": 1, "currency": "EUR"}], "categories": [],
               "transactions": [{"wallet_id": 7, "amount": 100, "date": DAY, "merchant": "Paris"}]}
    response = upload(person, profile)
    assert response.status_code == 400 and "Cash is in USD here and in EUR in the file" in response.json()["detail"]
    assert person.get("/api/transactions").json() == []
    fx._checked.clear()


def test_a_refused_shared_wallet_edit_changes_nothing(monkeypatch):
    monkeypatch.setattr(fx, "fetch", lambda currency: [(dt.date(2011, 1, 1), 0.5)] if currency == "EUR" else [])
    fx._checked.clear()
    owner, member = signup("hana"), signup("hugo")
    ledger = owner.post("/api/shared", json={"name": "Rome", "currency": "EUR", "members": ["hugo"]}).json()
    member.post(f"/api/shared/{ledger['id']}/accept")
    member.post("/api/transactions", json=expense(cash(member), amount=10, shared_wallet_id=ledger["id"]))
    fx._checked.clear()  # the next balance lookup fetches rates again, in the middle of the edit
    edit = {"name": "Renamed", "currency": "EUR", "members": []}  # removing hugo, who is still owed money
    assert owner.put(f"/api/shared/{ledger['id']}", json=edit).status_code == 409
    assert owner.get(f"/api/shared/{ledger['id']}").json()["name"] == "Rome"
    fx._checked.clear()
