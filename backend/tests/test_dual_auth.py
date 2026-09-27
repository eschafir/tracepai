from fastapi.testclient import TestClient

from app.main import app


def test_login_returns_token_and_cookie():
    with TestClient(app) as c:
        res = c.post("/api/auth/login", json={"username": "user", "password": "password"})
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "user"
        assert "token" in data
        assert "session_token" in res.cookies


def test_bearer_token_authentication():
    with TestClient(app) as c:
        # 1. Login to get token
        res = c.post("/api/auth/login", json={"username": "user", "password": "password"})
        assert res.status_code == 200
        token = res.json()["token"]

        # 2. Access with clean client (no cookies) using Bearer header
        clean_client = TestClient(app)
        res_me = clean_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me.status_code == 200
        assert res_me.json()["username"] == "user"

        # 3. Access without token fails
        res_unauth = clean_client.get("/api/auth/me")
        assert res_unauth.status_code == 401

        # 4. Logout via Bearer token
        res_logout = clean_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert res_logout.status_code == 200

        # 5. Subsequent access fails
        res_revoked = clean_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_revoked.status_code == 401


def test_signup_returns_token():
    with TestClient(app) as c:
        res = c.post("/api/auth/signup", json={"username": "new_mobile_user", "password": "password123"})
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "new_mobile_user"
        assert "token" in data
        token = data["token"]

        # Access with Bearer token
        clean = TestClient(app)
        res_me = clean.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res_me.status_code == 200
        assert res_me.json()["username"] == "new_mobile_user"
