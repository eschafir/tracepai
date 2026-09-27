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


def test_update_profile_display_name_and_password():
    with TestClient(app) as c:
        c.post("/api/auth/signup", json={"username": "profile_user", "password": "initial_password"})

        # 1. Update display name
        res = c.put("/api/auth/profile", json={"display_name": "Alice Wonderland"})
        assert res.status_code == 200
        assert res.json()["display_name"] == "Alice Wonderland"

        # Check /me reflects display name
        res_me = c.get("/api/auth/me")
        assert res_me.json()["display_name"] == "Alice Wonderland"

        # 2. Update password with wrong current password
        res_wrong = c.put("/api/auth/profile", json={"current_password": "wrong", "password": "new_password_123"})
        assert res_wrong.status_code == 400

        # 3. Update password successfully
        res_pw = c.put("/api/auth/profile", json={"current_password": "initial_password", "password": "new_password_123"})
        assert res_pw.status_code == 200

        # 4. Verify login with new password
        c.post("/api/auth/logout")
        res_relogin = c.post("/api/auth/login", json={"username": "profile_user", "password": "new_password_123"})
        assert res_relogin.status_code == 200

