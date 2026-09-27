import io
import json

from fastapi.testclient import TestClient

from app.main import app


def test_export_profile_structure(client: TestClient):
    res = client.get("/api/export/profile")
    assert res.status_code == 200
    assert "application/json" in res.headers["content-type"]
    assert "tracepai-profile-user.json" in res.headers["content-disposition"]

    data = res.json()
    assert data["version"] == 1
    assert "exported_at" in data
    assert "user" in data
    assert "budget_style" in data["user"]

    assert len(data["wallets"]) >= 4
    assert any(w["name"] == "Checking" for w in data["wallets"])
    assert any(w["name"] == "Savings" for w in data["wallets"])

    assert len(data["categories"]) >= 10
    assert any(c["name"] == "Groceries" for c in data["categories"])

    assert len(data["budgets"]) >= 1
    assert len(data["goals"]) >= 2
    assert len(data["recurring_rules"]) >= 1
    assert len(data["transactions"]) >= 10

    # Ensure splits are captured
    splits = [t for t in data["transactions"] if t.get("splits")]
    assert len(splits) > 0


def test_import_profile_clone_replace(client: TestClient):
    # 1. Export profile from seeded user
    res_export = client.get("/api/export/profile")
    assert res_export.status_code == 200
    profile_data = res_export.content

    # 2. Sign up a fresh user
    with TestClient(app) as clone_client:
        res_signup = clone_client.post(
            "/api/auth/signup", json={"username": "clone_tester", "password": "password123"}
        )
        assert res_signup.status_code == 200

        # Verify initial fresh account has only 1 Cash wallet and 0 transactions
        initial_wallets = clone_client.get("/api/wallets").json()
        assert len(initial_wallets) == 1
        assert initial_wallets[0]["name"] == "Cash"
        assert len(clone_client.get("/api/transactions").json()) == 0

        # 3. Import profile in replace mode
        files = {"file": ("backup.json", io.BytesIO(profile_data), "application/json")}
        res_import = clone_client.post("/api/import/profile", files=files, data={"mode": "replace"})
        assert res_import.status_code == 200
        result = res_import.json()
        assert result["ok"] is True
        assert result["imported"]["wallets"] >= 4
        assert result["imported"]["transactions"] >= 10

        # 4. Verify cloned account has all cloned resources
        cloned_wallets = clone_client.get("/api/wallets").json()
        wallet_names = {w["name"] for w in cloned_wallets}
        assert "Checking" in wallet_names
        assert "Credit card" in wallet_names
        assert "Savings" in wallet_names

        cloned_txns = clone_client.get("/api/transactions").json()
        assert len(cloned_txns) == result["imported"]["transactions"]

        cloned_goals = clone_client.get("/api/goals").json()
        assert len(cloned_goals) == result["imported"]["goals"]

        cloned_rules = clone_client.get("/api/recurring").json()
        assert len(cloned_rules) == result["imported"]["recurring_rules"]


def test_import_profile_merge_mode(client: TestClient):
    res_export = client.get("/api/export/profile")
    profile_data = res_export.content

    with TestClient(app) as merge_client:
        merge_client.post("/api/auth/signup", json={"username": "merge_tester", "password": "password123"})

        files = {"file": ("backup.json", io.BytesIO(profile_data), "application/json")}
        res_import = merge_client.post("/api/import/profile", files=files, data={"mode": "merge"})
        assert res_import.status_code == 200
        assert res_import.json()["ok"] is True


def test_import_profile_invalid_file(client: TestClient):
    files = {"file": ("bad.txt", io.BytesIO(b"not json at all"), "text/plain")}
    res = client.post("/api/import/profile", files=files)
    assert res.status_code == 400
    assert "valid JSON" in res.json()["detail"]

    files_bad_schema = {"file": ("bad.json", io.BytesIO(b'{"key": "value"}'), "application/json")}
    res2 = client.post("/api/import/profile", files=files_bad_schema)
    assert res2.status_code == 400
    assert "TracepAI profile" in res2.json()["detail"]
