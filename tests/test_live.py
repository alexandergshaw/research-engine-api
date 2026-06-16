"""Opt-in tests that hit REAL upstream sources. Run with: pytest --run-live

Skipped by default (see conftest). These validate connectors against live APIs;
they may be slow or flaky if a source is down or rate-limiting.
"""

import pytest


@pytest.mark.live
def test_live_concept_overview(client, auth):
    resp = client.post(
        "/v1/research",
        json={"intent": "concept.overview", "params": {"term": "HTTP"}},
        headers=auth,
    )
    assert resp.status_code == 200, resp.json
    assert resp.json["data"].get("summary")
    assert any(s["name"] == "wikipedia" for s in resp.json["sources"])


@pytest.mark.live
def test_live_academic_papers(client, auth):
    resp = client.get("/v1/academic/papers?query=transformer%20attention&limit=2", headers=auth)
    assert resp.status_code == 200, resp.json
    assert resp.json["data"]["papers"]


@pytest.mark.live
def test_live_company_profile(client, auth):
    resp = client.get("/v1/companies/AAPL/profile", headers=auth)
    assert resp.status_code == 200, resp.json
    assert "Apple" in resp.json["data"].get("name", "")
