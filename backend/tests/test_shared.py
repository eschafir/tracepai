from fastapi.testclient import TestClient

from app.main import app

DAY = "2013-05-10"  # a month no other test uses, so their totals don't change


def signup(username: str) -> TestClient:
    other = TestClient(app)
    response = other.post("/api/auth/signup", json={"username": username, "password": "secret-pass"})
    assert response.status_code == 200, response.text
    return other


def ids(client, path):
    return {x["name"]: x["id"] for x in client.get(path).json()}


def test_signup(client):
    ana = signup("ana")
    assert ana.get("/api/auth/me").json()["username"] == "ana"
    assert [(w["name"], w["balance"]) for w in ana.get("/api/wallets").json()] == [("Cash", 0)]
    assert {"Salary", "Rent", "Groceries", "Dining"} <= set(ids(ana, "/api/categories"))
    assert ana.get("/api/transactions").json() == [] and ana.get("/api/goals").json() == []
    assert ana.get("/api/analytics/summary").json()["expenses"] == 0

    assert TestClient(app).post("/api/auth/signup", json={"username": "ana", "password": "another-one"}).status_code == 409
    assert TestClient(app).post("/api/auth/signup", json={"username": "bo", "password": "secret-pass"}).status_code == 422
    assert TestClient(app).post("/api/auth/signup", json={"username": "bob", "password": "short"}).status_code == 422
    assert TestClient(app).post("/api/auth/signup", json={"username": "bob smith", "password": "secret-pass"}).status_code == 422
    login = TestClient(app).post("/api/auth/login", json={"username": "ana", "password": "secret-pass"})
    assert login.status_code == 200


def test_users_see_only_their_own_data(client):
    ben = signup("ben")
    mine = client.get("/api/transactions").json()
    assert ben.get("/api/transactions").json() == []
    assert ben.put(f"/api/transactions/{mine[0]['id']}", json={**mine[0], "amount": 1}).status_code == 404
    assert ben.delete(f"/api/wallets/{client.get('/api/wallets').json()[0]['id']}").status_code == 404
    assert ben.get("/api/analytics/networth").json()[-1]["net"] == 0
    home = client.post("/api/shared", json={"name": "Private", "currency": "USD"}).json()
    assert ben.get(f"/api/shared/{home['id']}").status_code == 404 and ben.get("/api/shared").json() == []
    client.delete(f"/api/shared/{home['id']}")


def test_shared_wallet(client):
    cara = signup("cara")
    mine, hers = ids(client, "/api/wallets"), ids(cara, "/api/wallets")
    my_cats, her_cats = ids(client, "/api/categories"), ids(cara, "/api/categories")
    pets = client.post("/api/categories", json={"name": "Pets 2013", "color_slot": 4}).json()["id"]
    home = client.post("/api/shared", json={"name": "Home", "currency": "usd"}).json()
    url = f"/api/shared/{home['id']}"
    assert home["currency"] == "USD" and [m["username"] for m in home["members"]] == ["user"]

    assert cara.post(f"{url}/members", json={"username": "user"}).status_code == 404  # not a member yet
    assert client.post(f"{url}/members", json={"username": "nobody"}).status_code == 404
    client.post(f"{url}/members", json={"username": "cara"})
    assert client.post(f"{url}/members", json={"username": "cara"}).status_code == 409
    assert cara.post(f"{url}/members", json={"username": "user"}).status_code == 403  # only the owner adds people

    checking_before = client.get("/api/wallets").json()[0]["balance"]
    expense = {"date": DAY, "kind": "expense", "shared_wallet_id": home["id"]}
    groceries = client.post("/api/transactions", json={**expense, "amount": 100, "merchant": "Market", "wallet_id": mine["Checking"],
                                                       "category_id": my_cats["Groceries"]}).json()
    dinner = cara.post("/api/transactions", json={**expense, "amount": 60, "merchant": "Bistro", "wallet_id": hers["Cash"],
                                                  "category_id": my_cats["Dining"]}).json()  # the owner's categories
    vet = client.post("/api/transactions", json={**expense, "amount": 40, "merchant": "Vet", "wallet_id": mine["Checking"],
                                                 "category_id": pets}).json()
    assert cara.post("/api/transactions", json={**expense, "kind": "income", "amount": 5, "wallet_id": hers["Cash"]}).status_code == 422
    stranger = signup("dan")
    dans_cash = ids(stranger, "/api/wallets")["Cash"]
    assert stranger.post("/api/transactions", json={**expense, "amount": 5, "wallet_id": dans_cash}).status_code == 404

    # The payer's own wallet pays the whole amount.
    assert client.get("/api/wallets").json()[0]["balance"] == round(checking_before - 140, 2)

    detail = client.get(url).json()
    uid = {m["username"]: m["id"] for m in detail["members"]}
    even = [{"user_id": uid["user"], "percent": 50.0}, {"user_id": uid["cara"], "percent": 50.0}]
    assert {e["merchant"]: e["shares"] for e in detail["expenses"]} == {n: even for n in ("Market", "Bistro", "Vet")}
    assert detail["balances"] == {str(uid["user"]): 40.0, str(uid["cara"]): -40.0}  # 50 + 20 - 30
    assert detail["debts"] == [{"from_user_id": uid["cara"], "to_user_id": uid["user"], "amount": 40.0}]
    assert cara.get(url).json()["balances"] == detail["balances"]

    # Personal analytics count each person's share, in their own categories.
    params = {"start": DAY, "end": DAY}
    my_totals = {c["name"]: c["total"] for c in client.get("/api/analytics/categories", params=params).json()}
    assert (my_totals["Groceries"], my_totals["Dining"], my_totals["Pets 2013"]) == (50, 30, 20)
    her_totals = {c["name"]: c["total"] for c in cara.get("/api/analytics/categories", params=params).json()}
    assert (her_totals["Groceries"], her_totals["Dining"], her_totals["Shared"]) == (50, 30, 20)  # she has no "Pets 2013"
    assert cara.get("/api/analytics/summary", params={"month": "2013-05"}).json()["expenses"] == 100
    # Filtering by one wallet shows only what that wallet paid, at your share.
    cash_only = cara.get("/api/analytics/categories", params={**params, "wallet": hers["Cash"]}).json()
    assert [(c["name"], c["total"]) for c in cash_only] == [("Dining", 30)]

    # Someone who joins later doesn't share earlier expenses.
    client.post(f"{url}/members", json={"username": "dan"})
    uid = {m["username"]: m["id"] for m in client.get(url).json()["members"]}
    assert client.get(url).json()["balances"][str(uid["dan"])] == 0

    # Settle up: cara pays 40 from her cash; it isn't spending or income for either of them.
    assert client.delete(f"{url}/members/{uid['cara']}").status_code == 409  # not settled yet
    assert cara.post(f"{url}/settlements", json={"from_user_id": uid["dan"], "to_user_id": uid["user"], "amount": 1,
                                                 "date": DAY}).status_code == 422  # only your own payments
    paid = cara.post(f"{url}/settlements", json={"from_user_id": uid["cara"], "to_user_id": uid["user"], "amount": 40, "date": DAY,
                                                 "wallet_id": hers["Cash"]}).json()
    assert client.get(url).json()["debts"] == []
    assert client.get(url).json()["settlements"][0]["recorded_by"] == [uid["cara"]]
    assert cara.post(f"/api/shared/settlements/{paid['id']}/record", json={"wallet_id": hers["Cash"]}).status_code == 409
    assert client.post(f"/api/shared/settlements/{paid['id']}/record", json={"wallet_id": mine["Checking"]}).status_code == 200
    assert cara.get("/api/analytics/summary", params={"month": "2013-05"}).json()["expenses"] == 100
    assert client.get("/api/analytics/summary", params={"month": "2013-05"}).json()["income"] == 0
    assert [w["balance"] for w in cara.get("/api/wallets").json()] == [-100]  # 60 dinner + 40 paid back
    assert client.get("/api/wallets").json()[0]["balance"] == round(checking_before - 100, 2)

    assert client.post(f"{url}/settlements", json={"from_user_id": uid["cara"], "to_user_id": uid["cara"], "amount": 1, "date": DAY}).status_code == 422
    assert cara.delete(f"{url}/members/{uid['cara']}").status_code == 200  # settled, so she can leave
    assert cara.get(url).status_code == 404

    client.delete(f"/api/shared/settlements/{paid['id']}")
    for t in (groceries, vet):
        client.delete(f"/api/transactions/{t['id']}")
    cara.delete(f"/api/transactions/{dinner['id']}")
    client.delete(f"{url}/members/{uid['dan']}")
    assert client.delete(url).status_code == 200
    client.delete(f"/api/categories/{pets}")


def test_percentages_editing_and_deleting(client):
    from app.shared import equal_shares, shares
    from app.models import Transaction

    assert shares(Transaction(shared_members="1,4")) == {1: 0.5, 4: 0.5}  # rows saved before percentages
    assert shares(Transaction(shared_members="1:70,4:30")) == {1: 0.7, 4: 0.3}
    assert equal_shares([1, 2, 3]) == {1: 33.33, 2: 33.33, 3: 33.34}

    eva = signup("eva")
    fede = signup("fede")
    mine, hers = ids(client, "/api/wallets"), ids(eva, "/api/wallets")
    before = {"mine": client.get("/api/wallets").json(), "hers": eva.get("/api/wallets").json()}
    assert client.post("/api/shared", json={"name": "Trip", "members": ["eva", "nobody"]}).status_code == 404
    assert all(s["name"] != "Trip" for s in client.get("/api/shared").json())  # nothing was created
    trip = client.post("/api/shared", json={"name": "Trip", "members": ["eva"]}).json()
    url = f"/api/shared/{trip['id']}"
    uid = {m["username"]: m["id"] for m in trip["members"]}
    assert set(uid) == {"user", "eva"} and trip["expense_count"] == 0 and trip["in_use"] is False

    expense = {"date": DAY, "kind": "expense", "amount": 100, "merchant": "Hotel", "wallet_id": mine["Checking"],
               "shared_wallet_id": trip["id"]}
    assert client.post("/api/transactions", json={**expense, "shares": {uid["user"]: 50, uid["eva"]: 40}}).status_code == 422
    fede_id = fede.get("/api/auth/me").json()["id"]
    assert client.post("/api/transactions", json={**expense, "shares": {uid["user"]: 50, fede_id: 50}}).status_code == 422
    hotel = client.post("/api/transactions", json={**expense, "shares": {uid["user"]: 70, uid["eva"]: 30}}).json()
    assert hotel["shared_members"] == f"{uid['user']}:70,{uid['eva']}:30"
    assert client.get(url).json()["balances"] == {str(uid["user"]): 30.0, str(uid["eva"]): -30.0}
    assert eva.get("/api/analytics/summary", params={"month": "2013-05"}).json()["expenses"] == 30

    # Only the payer can open, edit or delete it.
    assert eva.get(f"/api/transactions/{hotel['id']}").status_code == 404
    assert eva.put(f"/api/transactions/{hotel['id']}", json={**expense, "wallet_id": hers["Cash"]}).status_code == 404
    assert eva.delete(f"/api/transactions/{hotel['id']}").status_code == 404
    loaded = client.get(f"/api/transactions/{hotel['id']}").json()
    assert loaded["merchant"] == "Hotel"
    edited = client.put(f"/api/transactions/{hotel['id']}", json={**expense, "amount": 200, "shares": {uid["user"]: 50, uid["eva"]: 50}}).json()
    assert edited["shared_members"] == f"{uid['user']}:50,{uid['eva']}:50"
    assert client.get(url).json()["balances"][str(uid["eva"])] == -100
    kept = client.put(f"/api/transactions/{hotel['id']}", json={**expense, "amount": 80}).json()  # no shares: the split stays
    assert kept["shared_members"] == edited["shared_members"]

    # People are managed with the wallet: add fede, and eva can't be removed while she owes money.
    assert client.put(url, json={"name": "Trip", "members": ["fede"]}).status_code == 409
    renamed = client.put(url, json={"name": "Trip 2013", "members": ["eva", "fede"]}).json()
    assert renamed["name"] == "Trip 2013" and {m["username"] for m in renamed["members"]} == {"user", "eva", "fede"}
    assert renamed["expense_count"] == 1 and renamed["in_use"] is True
    assert client.put(url, json={"name": "Trip 2013", "members": ["eva"]}).status_code == 200  # fede is settled
    assert eva.put(url, json={"name": "Mine now", "members": []}).status_code == 403

    # Deleting it removes every expense in it, from every wallet, and the payments recorded for it.
    lunch = eva.post("/api/transactions", json={**expense, "merchant": "Lunch", "amount": 40, "wallet_id": hers["Cash"]}).json()
    paid = eva.post(f"{url}/settlements", json={"from_user_id": uid["eva"], "to_user_id": uid["user"], "amount": 20, "date": DAY,
                                                "wallet_id": hers["Cash"]}).json()
    client.post(f"/api/shared/settlements/{paid['id']}/record", json={"wallet_id": mine["Checking"]})
    assert eva.delete(url).status_code == 403
    assert client.delete(url).status_code == 200
    assert client.get(url).status_code == 404 and eva.get("/api/shared").json() == []
    assert all(t["id"] not in (hotel["id"], lunch["id"]) for t in client.get("/api/transactions").json() + eva.get("/api/transactions").json())
    assert not [t for t in client.get("/api/transactions").json() + eva.get("/api/transactions").json() if t["settlement_id"] == paid["id"]]
    assert client.get("/api/wallets").json() == before["mine"] and eva.get("/api/wallets").json() == before["hers"]


def test_shared_expense_without_a_shared_wallet(client):
    day, month = "2013-07-12", {"month": "2013-07"}  # a month no other test uses
    dan, eli = signup("dora"), signup("elio")
    mine, his = ids(client, "/api/wallets"), ids(dan, "/api/wallets")
    me = client.get("/api/auth/me").json()["id"]
    assert client.get("/api/auth/users/nobody").status_code == 404
    dan_id = client.get("/api/auth/users/dora").json()["id"]
    before = {"mine": client.get("/api/wallets").json(), "his": dan.get("/api/wallets").json()}
    dining = ids(client, "/api/categories")["Dining"]
    expense = {"date": day, "kind": "expense", "amount": 90, "merchant": "Dinner", "wallet_id": mine["Checking"],
               "category_id": dining, "tags": "friends"}

    assert client.post("/api/transactions", json={**expense, "shares": {me: 100}}).status_code == 422  # no one else
    assert client.post("/api/transactions", json={**expense, "shares": {me: 50, 99999: 50}}).status_code == 422
    assert client.post("/api/transactions", json={**expense, "shares": {me: 40, dan_id: 50}}).status_code == 422
    assert client.post("/api/transactions", json={**expense, "kind": "income", "category_id": None,
                                                  "shares": {me: 40, dan_id: 60}}).status_code == 422
    dinner = client.post("/api/transactions", json={**expense, "shares": {me: 40, dan_id: 60}}).json()
    assert dinner["shared_members"] == f"{me}:40,{dan_id}:60" and dinner["tags"] == "friends,shared"

    # Each person's spending is their share, in their own category with the same name.
    assert client.get("/api/analytics/summary", params=month).json()["expenses"] == 36
    assert dan.get("/api/analytics/summary", params=month).json()["expenses"] == 54
    params = {"start": "2013-07-01", "end": "2013-07-31"}
    assert {c["name"]: c["total"] for c in dan.get("/api/analytics/categories", params=params).json()} == {"Dining": 54}
    assert [t["id"] for t in dan.get("/api/transactions").json()] == []  # the money left my wallet, not his

    seen = dan.get("/api/shared-expenses").json()
    assert [s["id"] for s in seen] == [dinner["id"]] and seen[0]["paid_by"]["username"] == "user"
    assert [(s["username"], s["percent"], s["amount"], s["payment"]) for s in seen[0]["shares"]] == [
        ("user", 40, 36, None), ("dora", 60, 54, None)]
    assert eli.get("/api/shared-expenses").json() == [] and eli.get(f"/api/shared-expenses/{dinner['id']}").status_code == 404
    pay = f"/api/shared-expenses/{dinner['id']}/payments"
    assert eli.post(pay, json={"user_id": dan_id, "date": day}).status_code == 404
    assert client.post(pay, json={"user_id": me, "date": day}).status_code == 422  # the payer has nothing to pay back

    # Dan pays back from his wallet; I record it in mine. Neither is spending.
    paid = dan.post(pay, json={"user_id": dan_id, "date": day, "wallet_id": his["Cash"]}).json()
    payment = paid["shares"][1]["payment"]
    assert payment["recorded_by"] == [dan_id]
    assert dan.post(pay, json={"user_id": dan_id, "date": day}).status_code == 409
    assert client.post(f"/api/shared-expenses/payments/{payment['id']}/record", json={"wallet_id": his["Cash"]}).status_code == 404
    client.post(f"/api/shared-expenses/payments/{payment['id']}/record", json={"wallet_id": mine["Checking"]})
    assert eli.delete(f"/api/shared-expenses/payments/{payment['id']}").status_code == 404
    balance = lambda c, name: next(w["balance"] for w in c.get("/api/wallets").json() if w["name"] == name)  # noqa: E731
    assert balance(dan, "Cash") == next(w["balance"] for w in before["his"] if w["name"] == "Cash") - 54
    assert balance(client, "Checking") == next(w["balance"] for w in before["mine"] if w["name"] == "Checking") - 90 + 54
    assert client.get("/api/analytics/summary", params=month).json()["expenses"] == 36
    assert dan.get("/api/analytics/summary", params=month).json()["expenses"] == 54

    # Undoing the payment removes what it recorded, on both sides.
    unpaid = client.delete(f"/api/shared-expenses/payments/{payment['id']}").json()
    assert unpaid["shares"][1]["payment"] is None and dan.get("/api/wallets").json() == before["his"]

    # Taking dan off the expense, or deleting it, drops his payment too.
    dan.post(pay, json={"user_id": dan_id, "date": day, "wallet_id": his["Cash"]})
    solo = client.put(f"/api/transactions/{dinner['id']}", json={**expense, "shares": None}).json()
    assert solo["shared_members"] is None and dan.get("/api/shared-expenses").json() == []
    assert dan.get("/api/wallets").json() == before["his"]
    client.put(f"/api/transactions/{dinner['id']}", json={**expense, "shares": {me: 50, dan_id: 50}})
    dan.post(pay, json={"user_id": dan_id, "date": day, "wallet_id": his["Cash"]})
    client.delete(f"/api/transactions/{dinner['id']}")
    assert dan.get("/api/wallets").json() == before["his"] and client.get("/api/wallets").json() == before["mine"]
    assert dan.get("/api/analytics/summary", params=month).json()["expenses"] == 0
