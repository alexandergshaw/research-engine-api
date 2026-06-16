def test_health(client):
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_ready_lists_connectors(client):
    resp = client.get("/v1/ready")
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json["connectors"]}
    assert {"wikipedia", "wikidata"} <= names
