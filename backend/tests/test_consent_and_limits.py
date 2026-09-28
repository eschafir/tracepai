"""Sharing needs the other person's consent, repeating items can't start long ago, the login limit per username, and
editing an expense in a shared wallet you left (the high and medium items in docs/code_review.md)."""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.main import app

DAY = "2015-03-10"  # a month no other test uses
MONTH = {"month": DAY[:7]}
pytestmark = pytest.mark.usefixtures("client")  # starts the app, which creates the database


def signup(username: str) -> TestClient:
    person = TestClient(app, raise_server_exceptions=False)
    assert person.post("/api/auth/signup", json={"username": username, "password": "secret-pass"}).status_code == 200
    return person


def me(person: TestClient) -> int:
    return person.get("/api/auth/me").json()["id"]


def cash(person: TestClient) -> int:
    return next(w["id"] for w in person.get("/api/wallets").json() if w["name"] == "Cash")


def expense(wallet_id: int, **extra) -> dict:
    return {"date": DAY, "amount": 100, "kind": "expense", "merchant": "Shop", "wallet_id": wallet_id, **extra}


def spent(person: TestClient) -> float:
    return person.get("/api/analytics/summary", params=MONTH).json()["expenses"]


def test_direct_shares_count_only_once_accepted():
    stranger, victim, friend = signup("stan"), signup("vic"), signup("fran")
    spam = stranger.post("/api/transactions", json=expense(cash(stranger), shares={me(stranger): 1, me(victim): 99})).json()
    assert spent(victim) == 0 and victim.get("/api/shared-expenses").json() == []
    assert victim.post(f"/api/shared-expenses/{spam['id']}/payments", json={"user_id": me(victim), "date": DAY}).status_code == 404

    assert victim.post(f"/api/shared-expenses/people/{me(stranger)}/decline").status_code == 200
    assert victim.get("/api/shared/requests").json()["people"] == []  # declined: gone for good
    assert spent(victim) == 0
    shown = stranger.get(f"/api/shared-expenses/{spam['id']}").json()["shares"]
    assert [s["status"] for s in shown] == ["accepted", "declined"]

    # Accepting counts what the person already shared, and what they share later.
    friend.post("/api/transactions", json=expense(cash(friend), shares={me(friend): 50, me(victim): 50}))
    assert victim.post(f"/api/shared-expenses/people/{me(friend)}/accept").status_code == 200
    friend.post("/api/transactions", json=expense(cash(friend), shares={me(friend): 50, me(victim): 50}))
    assert spent(victim) == 100 and len(victim.get("/api/shared-expenses").json()) == 2
    assert victim.post(f"/api/shared-expenses/people/{me(victim)}/accept").status_code == 404
    assert victim.post("/api/shared-expenses/people/99999/accept").status_code == 404


def test_shared_wallet_invitations_must_be_accepted():
    owner, guest = signup("oksana"), signup("gus")
    ledger = owner.post("/api/shared", json={"name": "Cabin", "members": ["gus"]}).json()
    url = f"/api/shared/{ledger['id']}"
    assert [m["username"] for m in ledger["members"]] == ["oksana"] and [m["username"] for m in ledger["invited"]] == ["gus"]

    # The owner can't charge someone who hasn't accepted, and the guest can't use it yet.
    shares = {me(owner): 50, me(guest): 50}
    assert owner.post("/api/transactions", json=expense(cash(owner), shared_wallet_id=ledger["id"], shares=shares)).status_code == 422
    assert guest.post("/api/transactions", json=expense(cash(guest), shared_wallet_id=ledger["id"])).status_code == 404
    assert spent(guest) == 0

    assert guest.post(f"{url}/decline").status_code == 200
    assert owner.get(url).json()["invited"] == [] and guest.post(f"{url}/accept").status_code == 404

    owner.post(f"{url}/members", json={"username": "gus"})
    assert guest.post(f"{url}/accept").json()["members"][1]["username"] == "gus"
    owner.post("/api/transactions", json=expense(cash(owner), shared_wallet_id=ledger["id"], shares=shares))
    assert spent(guest) == 50


def test_repeating_items_start_at_most_a_year_ago():
    person = signup("rosalind")
    long_ago = (dt.date.today() - dt.timedelta(days=400)).isoformat()
    rule = {"amount": 9, "merchant": "Gym", "wallet_id": cash(person), "frequency": "weekly", "next_date": long_ago}
    response = person.post("/api/recurring", json=rule)
    assert response.status_code == 422 and "at most a year ago" in response.json()["detail"][0]["msg"]
    assert person.post("/api/transactions", json=expense(cash(person), date=long_ago, repeat="weekly")).status_code == 422
    assert person.post("/api/transactions", json=expense(cash(person), date=long_ago)).status_code == 200  # no repeat: fine
    assert person.get("/api/recurring").json() == []


def test_failed_logins_are_capped_per_username_whatever_the_client_address():
    signup("ivan")
    for i in range(50):  # a client behind a trusting proxy can claim a new address every time
        guesser = TestClient(app, client=(f"203.0.113.{i}", 50000))
        assert guesser.post("/api/auth/login", json={"username": "ivan", "password": "wrong-guess"}).status_code == 401
    fresh = TestClient(app, client=("198.51.100.77", 50000))
    assert fresh.post("/api/auth/login", json={"username": "ivan", "password": "secret-pass"}).status_code == 429


def test_a_former_member_can_edit_but_not_change_their_expense():
    owner, member = signup("omar"), signup("mona")
    url = f"/api/shared/{owner.post('/api/shared', json={'name': 'Flat'}).json()['id']}"
    ledger_id = int(url.rsplit("/", 1)[1])
    owner.post(f"{url}/members", json={"username": "mona"})
    member.post(f"{url}/accept")
    body = expense(cash(member), amount=20, shared_wallet_id=ledger_id)
    txn = member.post("/api/transactions", json=body).json()
    owner.post(f"{url}/settlements", json={"from_user_id": me(owner), "to_user_id": me(member), "amount": 10, "date": DAY})
    assert member.delete(f"{url}/members/{me(member)}").status_code == 200

    edited = member.put(f"/api/transactions/{txn['id']}", json={**body, "merchant": "Milk", "notes": "weekly shop"})
    assert edited.status_code == 200 and edited.json()["shared_members"] == txn["shared_members"]
    for change in ({"amount": 30}, {"date": "2015-03-11"}, {"shared_wallet_id": None}):
        assert member.put(f"/api/transactions/{txn['id']}", json={**body, **change}).status_code == 409
    assert member.delete(f"/api/transactions/{txn['id']}").status_code == 409
    assert owner.get(url).json()["balances"][str(me(owner))] == 0
