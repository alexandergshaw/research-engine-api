import httpx

from app import create_app
from app.config import TestConfig

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
AUTH = {"X-API-Key": "test-key"}

# Headline tones via the bundled lexicon: A=+4 (wins/record/profit/award),
# B=-2 (lawsuit/breach), C=0 (neutral).
ARTICLES = {
    "articles": [
        {"url": "https://reuters.com/a", "title": "Acme wins record profit and award",
         "seendate": "20260115T120000Z", "domain": "reuters.com", "language": "English"},
        {"url": "https://bloomberg.com/b", "title": "Acme faces lawsuit over data breach",
         "seendate": "20260120T120000Z", "domain": "bloomberg.com", "language": "English"},
        {"url": "https://wsj.com/c", "title": "Acme announces new product line",
         "seendate": "20260118T120000Z", "domain": "wsj.com", "language": "English"},
    ]
}


def _post(client, params, headers=AUTH):
    return client.post(
        "/v1/research", json={"intent": "company.news", "params": params}, headers=headers
    )


def test_returns_articles_sorted_by_tone_and_default_window(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json=ARTICLES))
    resp = _post(client, {"name": "Acme"})
    assert resp.status_code == 200, resp.json

    data = resp.json["data"]
    assert data["company"] == "Acme"
    assert data["as_of"]
    arts = data["articles"]
    # default min_tone 0.0 keeps A(+4) and C(0), drops B(-2); sorted tone desc
    assert [a["tone"] for a in arts] == [4.0, 0.0]
    assert arts[0]["title"].startswith("Acme wins")
    for a in arts:
        assert set(a.keys()) == {"title", "source", "url", "published", "tone", "language"}
        assert a["language"] == "en"
    # default recency window respected
    assert respx_mock.calls.last.request.url.params["timespan"] == "90d"


def test_min_tone_filters_below_threshold(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json=ARTICLES))
    resp = _post(client, {"name": "Acme", "min_tone": 1.0})
    assert [a["tone"] for a in resp.json["data"]["articles"]] == [4.0]  # only A survives


def test_sort_recency_reorders_by_date(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json=ARTICLES))
    resp = _post(client, {"name": "Acme", "min_tone": -10, "sort": "recency"})
    arts = resp.json["data"]["articles"]
    pubs = [a["published"] for a in arts]
    assert pubs == sorted(pubs, reverse=True)  # newest first
    assert arts[0]["url"].endswith("/b")  # B is the most recent (2026-01-20)


def test_obscure_name_returns_empty_with_no_news_warning(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json={"articles": []}))
    resp = _post(client, {"name": "Zzxqorg"})
    assert resp.status_code == 200, resp.json
    assert resp.json["data"]["articles"] == []
    assert "no news found for query" in resp.json["warnings"]
    assert resp.json["degraded"] is False


def test_company_news_works_inside_batch(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json=ARTICLES))
    body = {"requests": [{"intent": "company.news", "params": {"name": "Acme"}}]}
    resp = client.post("/v1/research/batch", json=body, headers=AUTH)
    assert resp.status_code == 200, resp.json
    result = resp.json["results"][0]
    assert result["intent"] == "company.news"
    assert result["data"]["articles"]


def test_attribution_present_and_no_body_text(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json=ARTICLES))
    env = _post(client, {"name": "Acme"}).json

    assert env["attribution_required"] is True
    assert all(s.get("attribution") for s in env["sources"])
    names = {s["name"] for s in env["sources"]}
    assert "gdelt" in names and "reuters.com" in names
    gdelt_src = next(s for s in env["sources"] if s["name"] == "gdelt")
    assert gdelt_src["attribution"].startswith("GDELT")
    for a in env["data"]["articles"]:  # headline + link + metadata only
        assert "body" not in a and "content" not in a
    assert env["data"]["as_of"]


def test_cache_hit_and_stable_etag_within_window(client, auth, respx_mock):
    respx_mock.get(GDELT).mock(return_value=httpx.Response(200, json=ARTICLES))
    r1 = _post(client, {"name": "Acme"})
    r2 = _post(client, {"name": "Acme"})
    assert r2.json["cache"]["hit"] is True
    assert r1.headers["ETag"] == r2.headers["ETag"]


class _DisabledNewsConfig(TestConfig):
    DISABLED_CONNECTORS = frozenset({"gdelt"})


def test_disabled_connector_returns_source_disabled_501():
    app = create_app(_DisabledNewsConfig)
    with app.app_context():
        resp = app.test_client().post(
            "/v1/research",
            json={"intent": "company.news", "params": {"name": "Acme"}},
            headers=AUTH,
        )
    assert resp.status_code == 501
    body = resp.get_json()
    assert body["code"] == "source_disabled"
    assert "gdelt" in body["disabled_sources"]
