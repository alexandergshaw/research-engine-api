from app import create_app
from app.config import TestConfig


def test_missing_key_is_401(client):
    resp = client.post(
        "/v1/research", json={"intent": "concept.overview", "params": {"term": "x"}}
    )
    assert resp.status_code == 401


def test_invalid_key_is_401(client):
    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {"term": "x"}},
        headers={"X-API-Key": "not-the-key"},
    )
    assert resp.status_code == 401


def test_intents_requires_key(client):
    assert client.get("/v1/intents").status_code == 401


def test_valid_key_allows_access(client, auth):
    resp = client.get("/v1/intents", headers=auth)
    assert resp.status_code == 200
    assert any(s["name"] == "concept.overview" for s in resp.json)


def test_open_mode_when_no_keys_configured():
    class OpenConfig(TestConfig):
        API_KEYS = frozenset()

    app = create_app(OpenConfig)
    with app.app_context():
        # No key needed when API_KEYS is empty.
        assert app.test_client().get("/v1/intents").status_code == 200
