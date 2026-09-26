import datetime as dt
import sqlite3

from app import db as app_db
from app.routers.analytics import pace_alert, projection

TODAY = dt.date.today()


def wallet(client, name):
    return next(w["id"] for w in client.get("/api/wallets").json() if w["name"] == name)


# Pace alerts


def test_projection_keeps_recurring_out_of_the_pace():
    # Rent of 1500 posted on the 1st by a recurring item: on day 10 of 30 it stays 1500, no alert.
    rent = projection(spent=1500, fixed=1500, upcoming=0, elapsed=10, days=30)
    assert rent == 1500 and pace_alert(1500, rent, 1600, 10) is None
    # Dining at 200 by day 10 is on pace for 600, over a 350 limit.
    dining = projection(spent=200, fixed=0, upcoming=0, elapsed=10, days=30)
    assert dining == 600 and pace_alert(200, dining, 350, 10) == "pace"
    # Too early in the month to judge the pace, but being over already always counts.
    assert pace_alert(100, 1000, 350, 4) is None and pace_alert(400, 400, 350, 2) == "over"
    # A subscription still due later this month is added once, not extrapolated.
    assert projection(spent=0, fixed=0, upcoming=15.49, elapsed=10, days=30) == 15.49


def test_budget_rows_have_projection(client):
    rows = client.get("/api/analytics/budgets").json()
    assert rows and all("projected" in r and r["alert"] in (None, "over", "pace") for r in rows)
    assert all(r["projected"] >= r["spent"] for r in rows)
    past = client.get("/api/analytics/budgets", params={"month": "2014-03"}).json()
    assert all(r["alert"] is None and r["projected"] == r["spent"] for r in past)


# Monthly goal transfers


def test_goal_repeats_monthly(client):
    checking, savings = wallet(client, "Checking"), wallet(client, "Savings")
    goal = client.post("/api/goals", json={"name": "Bike", "target_amount": 900, "wallet_id": savings}).json()
    url = f"/api/goals/{goal['id']}/contributions"
    started = TODAY - dt.timedelta(days=40)  # so next month's transfer is already due
    add = {"date": started.isoformat(), "amount": 100, "direction": "in", "wallet_id": checking, "repeat": "monthly"}
    assert client.post(url, json={**add, "direction": "out"}).status_code == 422

    client.post(url, json=add)
    goal = next(g for g in client.get("/api/goals").json() if g["id"] == goal["id"])
    assert goal["saved"] == 200 and len(goal["repeating"]) == 1  # the first transfer and next month's
    rule = goal["repeating"][0]
    assert rule["amount"] == 100 and rule["wallet_id"] == checking and rule["next_date"] > TODAY.isoformat()
    assert [c["amount"] for c in client.get(url).json()] == [100, 100]

    # A recurring item linked to the goal must touch the goal's wallet.
    bad = {"kind": "transfer", "amount": 5, "wallet_id": checking, "to_wallet_id": wallet(client, "Cash"),
           "goal_id": goal["id"], "frequency": "monthly", "next_date": (TODAY + dt.timedelta(days=5)).isoformat()}
    assert client.post("/api/recurring", json=bad).status_code == 422

    # Deleting the goal stops its monthly transfer and keeps the past ones.
    client.delete(f"/api/goals/{goal['id']}")
    assert all(r["id"] != rule["rule_id"] for r in client.get("/api/recurring").json())
    kept = [t for t in client.get("/api/transactions", params={"q": "Bike"}).json()]
    assert len(kept) == 2 and all(t["goal_id"] is None for t in kept)
    for t in kept:
        client.delete(f"/api/transactions/{t['id']}")


# Price changes


def test_price_changes(client):
    checking = wallet(client, "Checking")
    rule = client.post("/api/recurring", json={"kind": "expense", "amount": 10, "merchant": "StreamCo", "wallet_id": checking,
                                               "frequency": "monthly", "next_date": (TODAY + dt.timedelta(days=20)).isoformat()}).json()
    changes = lambda: [c for c in client.get("/api/recurring/price-changes").json() if c["rule_id"] == rule["id"]]
    assert changes() == []

    charge = {"date": TODAY.isoformat(), "amount": 12.99, "kind": "expense", "merchant": "STREAMCO", "wallet_id": checking}
    first = client.post("/api/transactions", json=charge).json()
    assert [(c["old"], c["new"]) for c in changes()] == [(10, 12.99)]

    assert client.post(f"/api/recurring/{rule['id']}/keep-price", json={"amount": 12.99}).status_code == 200
    assert changes() == []
    second = client.post("/api/transactions", json={**charge, "amount": 13.99}).json()
    assert [c["new"] for c in changes()] == [13.99]  # a different new price alerts again

    client.put(f"/api/recurring/{rule['id']}", json={**rule, "amount": 13.99})
    assert changes() == []
    small = client.post("/api/transactions", json={**charge, "amount": 14.2}).json()
    assert changes() == []  # 0.21 is under the $0.50 threshold

    for t in (first, second, small):
        client.delete(f"/api/transactions/{t['id']}")
    client.delete(f"/api/recurring/{rule['id']}")


# Budget styles and year in review


def test_budget_plan_and_year(client):
    checking = wallet(client, "Checking")
    made = []

    def category(name, group, kind="expense"):
        c = client.post("/api/categories", json={"name": name, "color_slot": 1, "kind": kind, "budget_group": group}).json()
        made.append(("categories", c["id"]))
        return c["id"]

    def txn(day, amount, kind, cat, merchant="Shop"):
        t = client.post("/api/transactions", json={"date": f"2014-03-{day:02d}", "amount": amount, "kind": kind, "merchant": merchant,
                                                   "wallet_id": checking, "category_id": cat}).json()
        made.append(("transactions", t["id"]))

    job, rent, fun, misc, invest = (category("Job 2014", None, "income"), category("Rent 2014", "need"),
                                    category("Fun 2014", "want"), category("Misc 2014", None), category("Invest 2014", "savings"))
    txn(1, 1000, "income", job)
    txn(2, 400, "expense", rent, "Landlord")
    txn(5, 150, "expense", fun, "Cinema")
    txn(9, 50, "expense", fun, "Cinema")
    txn(12, 100, "expense", misc)
    txn(20, 50, "expense", invest)

    plan = client.get("/api/analytics/budget-plan", params={"month": "2014-03"}).json()
    groups = {g["group"]: g for g in plan["groups"]}
    assert plan["income"] == 1000 and plan["left_to_assign"] == round(1000 - plan["assigned"], 2)
    assert (groups["need"]["actual"], groups["want"]["actual"], groups["savings"]["actual"]) == (400, 300, 300)
    assert (groups["need"]["target"], groups["want"]["target"], groups["savings"]["target"]) == (500, 300, 200)
    assert "Misc 2014" in plan["ungrouped"] and "Rent 2014" not in plan["ungrouped"]

    edited = client.put(f"/api/categories/{misc}", json={"name": "Misc 2014", "color_slot": 1, "budget_group": "need"}).json()
    assert edited["budget_group"] == "need"
    assert client.put(f"/api/categories/{misc}", json={"name": "X", "color_slot": 1, "budget_group": "other"}).status_code == 422

    year = client.get("/api/analytics/year", params={"year": 2014}).json()
    assert (year["income"], year["expenses"], year["net"], year["savings_rate"]) == (1000, 750, 250, 25)
    assert year["busiest_month"] == {"month": "2014-03", "expense": 750} and len(year["months"]) == 12
    assert year["categories"][0]["name"] == "Rent 2014" and year["categories"][0]["share"] == 53.3
    assert year["largest"][0]["amount"] == 400 and year["frequent"][0] == {"merchant": "Cinema", "count": 2, "total": 200}
    assert year["previous_expenses"] == 0 and year["change_percent"] is None
    assert year["net_worth_end"] - year["net_worth_start"] == 250
    empty = client.get("/api/analytics/year", params={"year": 2013}).json()
    assert (empty["income"], empty["expenses"], empty["busiest_month"], empty["categories"]) == (0, 0, None, [])

    for kind, id_ in reversed(made):
        client.delete(f"/api/{kind}/{id_}")


def test_settings(client):
    assert client.get("/api/settings").json() == {"budget_style": "limits"}
    assert client.put("/api/settings", json={"budget_style": "50_30_20"}).json() == {"budget_style": "50_30_20"}
    assert client.get("/api/settings").json() == {"budget_style": "50_30_20"}
    assert client.put("/api/settings", json={"budget_style": "envelopes"}).status_code == 422
    client.put("/api/settings", json={"budget_style": "limits"})


def test_old_users_get_limits_style(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR, password_hash VARCHAR)")
    con.execute("INSERT INTO user VALUES (1, 'user', 'x')")
    con.commit()
    con.close()
    monkeypatch.setattr(app_db, "engine", app_db.create_engine(f"sqlite:///{path}"))
    app_db.add_missing_columns()
    con = sqlite3.connect(path)
    assert con.execute("SELECT budget_style FROM user").fetchall() == [("limits",)]
    con.close()
