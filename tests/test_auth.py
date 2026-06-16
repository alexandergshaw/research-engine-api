from app.auth.models import ApiKey, Tenant
from app.extensions import db


def test_missing_api_key_is_401(client):
    resp = client.post(
        "/v1/research", json={"intent": "concept.overview", "params": {"term": "x"}}
    )
    assert resp.status_code == 401


def test_invalid_api_key_is_401(client):
    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {"term": "x"}},
        headers={"X-API-Key": "rek_not-a-real-key"},
    )
    assert resp.status_code == 401


def test_intents_requires_auth_and_lists_sources(client, auth):
    assert client.get("/v1/intents").status_code == 401

    resp = client.get("/v1/intents", headers=auth)
    assert resp.status_code == 200
    overview = next(s for s in resp.json if s["name"] == "concept.overview")
    assert "wikipedia" in overview["sources"]


def test_usage_is_logged(client, auth, respx_mock):
    import httpx

    respx_mock.get("https://en.wikipedia.org/api/rest_v1/page/summary/RSA").mock(
        return_value=httpx.Response(
            200,
            json={"title": "RSA", "extract": "x", "content_urls": {"desktop": {"page": "u"}}},
        )
    )
    respx_mock.get("https://www.wikidata.org/w/api.php").mock(
        return_value=httpx.Response(200, json={"search": []})
    )

    client.get("/v1/concepts/RSA/overview", headers=auth)

    from app.auth.models import UsageLog

    logs = UsageLog.query.all()
    assert len(logs) == 1
    assert logs[0].intent == "concept.overview"
    assert "wikipedia" in (logs[0].sources or "")
    assert logs[0].status == 200


def test_inactive_key_rejected(client):
    tenant = Tenant(name="t2")
    db.session.add(tenant)
    db.session.flush()
    key, raw = ApiKey.generate(tenant)
    key.active = False
    db.session.add(key)
    db.session.commit()

    resp = client.get("/v1/intents", headers={"X-API-Key": raw})
    assert resp.status_code == 401
