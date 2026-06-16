from urllib.parse import quote

import httpx

WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIDATA = "https://www.wikidata.org/w/api.php"


def test_research_overview_merges_and_attributes(client, auth, respx_mock):
    title = quote("TLS_handshake", safe="")
    respx_mock.get(f"{WIKI}/{title}").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Transport Layer Security",
                "extract": "TLS is a cryptographic protocol that provides security.",
                "description": "cryptographic protocol",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/TLS"}},
                "thumbnail": {"source": "https://example/thumb.png"},
            },
        )
    )
    respx_mock.get(WIKIDATA).mock(return_value=httpx.Response(200, json={"search": []}))

    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {"term": "TLS handshake"}},
        headers=auth,
    )

    assert resp.status_code == 200, resp.json
    body = resp.json
    assert body["data"]["summary"].startswith("TLS is a cryptographic")
    assert body["degraded"] is False
    assert any(s["name"] == "wikipedia" for s in body["sources"])
    assert body["sources"][0]["license"] == "CC BY-SA 4.0"


def test_degraded_when_a_source_fails_but_another_succeeds(client, auth, respx_mock):
    respx_mock.get(f"{WIKI}/Python").mock(return_value=httpx.Response(500))

    def wikidata_router(request):
        if request.url.params.get("action") == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q28865"}]})
        return httpx.Response(
            200,
            json={
                "entities": {
                    "Q28865": {
                        "labels": {"en": {"value": "Python"}},
                        "descriptions": {"en": {"value": "programming language"}},
                        "aliases": {},
                        "claims": {},
                    }
                }
            },
        )

    respx_mock.get(WIKIDATA).mock(side_effect=wikidata_router)

    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {"term": "Python"}},
        headers=auth,
    )

    assert resp.status_code == 200, resp.json
    body = resp.json
    assert body["degraded"] is True
    assert body["data"]["label"] == "Python"
    assert any("wikipedia" in w for w in body["warnings"])


def test_all_sources_fail_returns_502(client, auth, respx_mock):
    respx_mock.get(f"{WIKI}/Nonexistixx").mock(return_value=httpx.Response(503))
    respx_mock.get(WIKIDATA).mock(return_value=httpx.Response(503))

    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {"term": "Nonexistixx"}},
        headers=auth,
    )
    assert resp.status_code == 502


def test_unknown_intent_is_422(client, auth):
    resp = client.post(
        "/v1/research",
        json={"intent": "bogus.intent", "params": {"term": "x"}},
        headers=auth,
    )
    assert resp.status_code == 422


def test_missing_required_param_is_422(client, auth):
    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {}},
        headers=auth,
    )
    assert resp.status_code == 422


def test_granular_concept_endpoint(client, auth, respx_mock):
    respx_mock.get(f"{WIKI}/RSA").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "RSA",
                "extract": "RSA is a public-key cryptosystem.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/RSA"}},
            },
        )
    )
    respx_mock.get(WIKIDATA).mock(return_value=httpx.Response(200, json={"search": []}))

    resp = client.get("/v1/concepts/RSA/overview", headers=auth)
    assert resp.status_code == 200, resp.json
    assert resp.json["data"]["title"] == "RSA"
