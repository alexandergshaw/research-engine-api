import httpx

from app import create_app
from app.config import TestConfig
from app.core.mapping import decode_cursor

SOURCE_URL = "https://jobs.example.com/api"
AUTH = {"X-API-Key": "test-key"}

# A caller-supplied source spec: where to fetch + how to read it.
SOURCE = {
    "url": SOURCE_URL,
    "items_path": "data.jobs",
    "map": {
        "id": "id",
        "title": "title",
        "company": "company.name",
        "location": "location",
        "url": "url",
        "posted_at": "updated_at",
    },
    "cursor_field": "posted_at",
    "cursor_type": "datetime",
}

# Three postings; job 2 is newest, job 3 oldest (by updated_at).
PAYLOAD = {
    "data": {
        "jobs": [
            {"id": "1", "title": "Senior Engineer", "company": {"name": "Acme"},
             "location": "Remote", "url": "https://acme.example.com/jobs/1",
             "updated_at": "2026-06-15T10:00:00Z"},
            {"id": "2", "title": "Staff Engineer", "company": {"name": "Acme"},
             "location": "NYC", "url": "https://acme.example.com/jobs/2",
             "updated_at": "2026-06-16T12:00:00Z"},
            {"id": "3", "title": "Junior Engineer", "company": {"name": "Acme"},
             "location": "Remote", "url": "https://acme.example.com/jobs/3",
             "updated_at": "2026-06-14T08:00:00Z"},
        ]
    }
}


def _post(client, body, headers=AUTH):
    return client.post("/v1/jobs/postings", json=body, headers=headers)


def test_projects_and_orders_by_cursor_desc(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    resp = _post(client, {"source": SOURCE})
    assert resp.status_code == 200, resp.json

    data = resp.json["data"]
    assert data["source"] == "jobs.example.com"
    assert data["as_of"]
    assert data["count"] == 3 and data["has_more"] is False
    assert data["cursor"]  # opaque high-water token

    postings = data["postings"]
    assert [p["id"] for p in postings] == ["2", "1", "3"]  # newest first
    assert postings[0]["title"] == "Staff Engineer"
    assert postings[0]["company"] == "Acme"  # dotted path company.name
    assert postings[0]["location"] == "NYC"
    # cursor decodes to the newest posted_at
    value, ctype = decode_cursor(data["cursor"])
    assert value == "2026-06-16T12:00:00Z" and ctype == "datetime"


def test_since_returns_only_strictly_newer_items(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    # job 1's own timestamp — strict '>' excludes job 1, keeps only job 2.
    resp = _post(client, {"source": SOURCE, "since": "2026-06-15T10:00:00Z"})
    assert [p["id"] for p in resp.json["data"]["postings"]] == ["2"]


def test_cursor_roundtrip_yields_no_new_items(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    first = _post(client, {"source": SOURCE}).json["data"]
    # Polling again with the returned cursor: nothing is newer than the high-water mark.
    resp = _post(client, {"source": SOURCE, "cursor": first["cursor"]})
    data = resp.json["data"]
    assert data["postings"] == []
    assert data["count"] == 0
    assert "no new items since cursor" in resp.json["warnings"]
    assert data["cursor"] == first["cursor"]  # echoes the cursor so polling can continue


def test_limit_caps_page_and_sets_has_more(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    resp = _post(client, {"source": SOURCE, "limit": 2})
    data = resp.json["data"]
    assert [p["id"] for p in data["postings"]] == ["2", "1"]
    assert data["has_more"] is True and data["count"] == 2


def test_works_via_generic_research_endpoint(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    resp = client.post(
        "/v1/research", json={"intent": "feed.poll", "params": {"source": SOURCE}}, headers=AUTH
    )
    assert resp.status_code == 200, resp.json
    assert resp.json["data"]["postings"]


def test_auth_headers_are_redacted_in_echoed_query(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    src = {**SOURCE, "headers": {"Authorization": "Bearer super-secret-token"}}
    resp = _post(client, {"source": src})
    assert resp.status_code == 200, resp.json
    assert resp.json["query"]["source"]["headers"] == {"Authorization": "***"}
    assert "super-secret-token" not in resp.get_data(as_text=True)


def test_missing_url_is_a_client_error(client, respx_mock):
    # Via the generic endpoint (no schema pre-check) the connector rejects -> 422.
    resp = client.post(
        "/v1/research",
        json={"intent": "feed.poll", "params": {"source": {"foo": "bar"}}},
        headers=AUTH,
    )
    assert resp.status_code == 422


def test_non_json_source_is_rejected(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, text="<html>nope</html>"))
    resp = _post(client, {"source": SOURCE})
    assert resp.status_code == 422


def test_redirects_are_not_followed(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://elsewhere.example.com/x"})
    )
    resp = _post(client, {"source": SOURCE})
    assert resp.status_code == 422


def test_cache_hit_and_stable_etag_within_window(client, respx_mock):
    respx_mock.get(SOURCE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    r1 = _post(client, {"source": SOURCE})
    r2 = _post(client, {"source": SOURCE})
    assert r2.json["cache"]["hit"] is True
    assert r1.headers["ETag"] == r2.headers["ETag"]


# --- SSRF guard (re-enables private-target blocking) -----------------------
class _SsrfConfig(TestConfig):
    DYNAMIC_SOURCE_BLOCK_PRIVATE = True


def _ssrf_post(url):
    app = create_app(_SsrfConfig)
    with app.app_context():
        return app.test_client().post(
            "/v1/research",
            json={"intent": "feed.poll", "params": {"source": {"url": url, "map": {}}}},
            headers=AUTH,
        )


def test_ssrf_blocks_loopback():
    resp = _ssrf_post("https://127.0.0.1/jobs")
    assert resp.status_code == 422
    assert "rejected" in resp.get_json()["message"]


def test_ssrf_blocks_cloud_metadata():
    resp = _ssrf_post("https://169.254.169.254/latest/meta-data/")
    assert resp.status_code == 422


def test_ssrf_blocks_ipv4_mapped_loopback():
    resp = _ssrf_post("https://[::ffff:127.0.0.1]/jobs")  # IPv4-mapped IPv6 bypass attempt
    assert resp.status_code == 422


def test_ssrf_blocks_ipv4_mapped_metadata():
    resp = _ssrf_post("https://[::ffff:169.254.169.254]/latest/meta-data/")
    assert resp.status_code == 422


def test_ssrf_blocks_plain_http_by_default():
    resp = _ssrf_post("http://jobs.example.com/api")  # https required unless allowed
    assert resp.status_code == 422


# --- Per-deploy disablement -------------------------------------------------
class _DisabledJobsConfig(TestConfig):
    DISABLED_CONNECTORS = frozenset({"http_source"})


def test_disabled_connector_returns_source_disabled_501():
    app = create_app(_DisabledJobsConfig)
    with app.app_context():
        resp = app.test_client().post(
            "/v1/research",
            json={"intent": "feed.poll", "params": {"source": SOURCE}},
            headers=AUTH,
        )
    assert resp.status_code == 501
    body = resp.get_json()
    assert body["code"] == "source_disabled"
    assert "http_source" in body["disabled_sources"]
