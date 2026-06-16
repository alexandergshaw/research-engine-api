import httpx

from app import create_app
from app.config import TestConfig

WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIDATA = "https://www.wikidata.org/w/api.php"
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
AUTH = {"X-API-Key": "test-key"}


def _mock_wikipedia(respx_mock, slug, title="RSA"):
    respx_mock.get(f"{WIKI}/{slug}").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": title,
                "extract": "RSA is a public-key cryptosystem.",
                "content_urls": {"desktop": {"page": f"https://en.wikipedia.org/wiki/{slug}"}},
            },
        )
    )
    respx_mock.get(WIKIDATA).mock(return_value=httpx.Response(200, json={"search": []}))


# --- attribution -----------------------------------------------------------
def test_wikipedia_result_has_attribution_and_flag(client, respx_mock):
    _mock_wikipedia(respx_mock, "RSA")
    resp = client.get("/v1/concepts/RSA/overview", headers=AUTH)
    assert resp.status_code == 200, resp.json

    src = next(s for s in resp.json["sources"] if s["name"] == "wikipedia")
    assert src["attribution"] == "Wikipedia — CC BY-SA 4.0 — https://en.wikipedia.org/wiki/RSA"
    assert resp.json["attribution_required"] is True
    assert resp.json["meta"]["version"]  # present


def test_public_domain_only_result_does_not_require_attribution(client, respx_mock):
    respx_mock.get(NVD).mock(
        return_value=httpx.Response(
            200,
            json={
                "totalResults": 1,
                "vulnerabilities": [
                    {"cve": {"id": "CVE-1", "descriptions": [{"lang": "en", "value": "x"}],
                             "metrics": {}, "references": []}}
                ],
            },
        )
    )
    resp = client.get("/v1/security/vulnerabilities?product=openssl", headers=AUTH)
    assert resp.status_code == 200, resp.json
    assert resp.json["attribution_required"] is False  # NVD is public domain


# --- ETag + version --------------------------------------------------------
def test_etag_is_deterministic_for_same_intent_params_version(client, respx_mock):
    _mock_wikipedia(respx_mock, "RSA")
    r1 = client.get("/v1/concepts/RSA/overview", headers=AUTH)
    r2 = client.get("/v1/concepts/RSA/overview", headers=AUTH)
    assert r1.headers.get("ETag")
    assert r1.headers["ETag"] == r2.headers["ETag"]
    assert r1.headers["Cache-Control"].startswith("public")


def test_version_endpoint(client):
    resp = client.get("/v1/version")  # no auth
    assert resp.status_code == 200
    assert resp.json["version"]
    assert resp.json["api"] == "v1"


# --- batch -----------------------------------------------------------------
def test_batch_preserves_order_and_isolates_failures(client, respx_mock):
    _mock_wikipedia(respx_mock, "TLS", title="TLS")
    body = {
        "requests": [
            {"intent": "concept.overview", "params": {"term": "TLS"}},
            {"intent": "bogus.intent", "params": {"term": "x"}},
        ]
    }
    resp = client.post("/v1/research/batch", json=body, headers=AUTH)
    assert resp.status_code == 200, resp.json
    results = resp.json["results"]
    assert len(results) == 2

    # order preserved
    assert results[0]["intent"] == "concept.overview"
    assert results[1]["intent"] == "bogus.intent"
    # first succeeds, second is an isolated degraded result
    assert results[0]["data"].get("summary")
    assert results[0]["degraded"] is False
    assert results[1]["degraded"] is True
    assert results[1]["data"] == {}
    assert results[1]["warnings"]
    # every batch item carries meta.version
    assert all(r["meta"]["version"] for r in results)
    assert resp.headers["Cache-Control"] == "no-store"


def test_batch_over_cap_is_422(client):
    body = {"requests": [{"intent": "concept.definition", "params": {"term": "x"}}] * 21}
    resp = client.post("/v1/research/batch", json=body, headers=AUTH)
    assert resp.status_code == 422


def test_batch_rate_limit_cost_counts_each_subrequest():
    class LimitedBatchConfig(TestConfig):
        RATELIMIT_ENABLED = True
        RATELIMIT_DEFAULT = "3/minute"
        RATELIMIT_STORAGE_URI = "memory://"

    app = create_app(LimitedBatchConfig)
    body = {
        "requests": [
            {"intent": "bogus.a", "params": {"term": "x"}},
            {"intent": "bogus.b", "params": {"term": "y"}},
        ]
    }
    with app.app_context():
        client = app.test_client()
        r1 = client.post("/v1/research/batch", json=body, headers=AUTH)  # cost 2 (≤3)
        r2 = client.post("/v1/research/batch", json=body, headers=AUTH)  # cost 2 (>1 left)
    assert r1.status_code == 200
    assert r2.status_code == 429


# --- source disabled -------------------------------------------------------
class DisabledConfig(TestConfig):
    DISABLED_CONNECTORS = frozenset({"mitre_attack"})


def test_source_disabled_returns_structured_501():
    app = create_app(DisabledConfig)
    with app.app_context():
        resp = app.test_client().get("/v1/security/techniques?query=phishing", headers=AUTH)
    assert resp.status_code == 501
    body = resp.get_json()
    assert body["code"] == "source_disabled"
    assert "mitre_attack" in body["disabled_sources"]
    assert body.get("detail")


def test_ready_reports_disabled_source():
    app = create_app(DisabledConfig)
    with app.app_context():
        resp = app.test_client().get("/v1/ready")
    body = resp.get_json()
    assert "mitre_attack" in body["disabled_sources"]
    mitre = next(c for c in body["connectors"] if c["name"] == "mitre_attack")
    assert mitre["disabled"] is True
