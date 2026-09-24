import os
import tempfile

os.environ["TRACEPAI_DATA_DIR"] = tempfile.mkdtemp()

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "user", "password": "password"}).status_code == 200
        yield c
