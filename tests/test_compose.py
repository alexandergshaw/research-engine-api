import httpx

WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary"
WIKIDATA = "https://www.wikidata.org/w/api.php"
STACKEXCHANGE = "https://api.stackexchange.com/2.3/search/advanced"
GITHUB = "https://api.github.com/search/repositories"
ARXIV = "https://export.arxiv.org/api/query"

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>On TLS 1.3</title>
    <summary>Analysis.</summary>
    <id>http://arxiv.org/abs/2000.0001</id>
    <published>2021-01-01T00:00:00Z</published>
    <author><name>A. Researcher</name></author>
  </entry>
</feed>"""


def test_slide_outline_composes_multiple_sources(client, auth, respx_mock):
    respx_mock.get(f"{WIKI}/TLS").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Transport Layer Security",
                "extract": "TLS is a protocol. It secures traffic. It is widely used.",
                "description": "cryptographic protocol",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/TLS"}},
            },
        )
    )
    respx_mock.get(WIKIDATA).mock(return_value=httpx.Response(200, json={"search": []}))
    respx_mock.get(STACKEXCHANGE).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "How does the TLS handshake work?",
                        "link": "https://stackoverflow.com/q/9",
                        "score": 10,
                        "is_answered": True,
                        "answer_count": 2,
                        "tags": ["tls", "security"],
                    }
                ]
            },
        )
    )
    respx_mock.get(GITHUB).mock(return_value=httpx.Response(200, json={"items": []}))
    respx_mock.get(ARXIV).mock(return_value=httpx.Response(200, text=ARXIV_XML))

    resp = client.get("/v1/compose/slide-outline?topic=TLS", headers=auth)
    assert resp.status_code == 200, resp.json
    data = resp.json["data"]
    types = [s["type"] for s in data["slides"]]
    assert types[0] == "title"
    assert "overview" in types
    assert "key_terms" in types
    assert "examples" in types
    assert "references" in types
    assert "sources" in types
    # provenance spans all three contributing sources
    names = {s["name"] for s in resp.json["sources"]}
    assert {"wikipedia", "stackexchange", "arxiv"} <= names
    assert resp.json["degraded"] is False
