from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version():
    r = client.get("/version")
    assert r.json()["service"] == "template-svc"


def test_ping():
    r = client.get("/api/ping")
    assert r.json() == {"pong": True}


def test_echo():
    r = client.post("/api/echo", json={"message": "hi"})
    assert r.json() == {"message": "hi", "length": 2}


def test_whoami_requires_auth():
    r = client.get("/api/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["type"] == "http_error"
