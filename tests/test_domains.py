import httpx

STACKEXCHANGE = "https://api.stackexchange.com/2.3/search/advanced"
GITHUB = "https://api.github.com/search/repositories"
NVD = "https://services.nvd.nist.gov/rest/json/cves/2.0"
ARXIV = "https://export.arxiv.org/api/query"
MITRE = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    "enterprise-attack/enterprise-attack.json"
)

ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>A Study of Transformers</title>
    <summary>We study attention.</summary>
    <id>http://arxiv.org/abs/1234.5678</id>
    <published>2020-01-01T00:00:00Z</published>
    <author><name>Jane Doe</name></author>
    <author><name>John Roe</name></author>
  </entry>
</feed>"""


def test_concept_examples_combines_stackexchange_and_github(client, auth, respx_mock):
    respx_mock.get(STACKEXCHANGE).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "How to use asyncio?",
                        "link": "https://stackoverflow.com/q/1",
                        "score": 42,
                        "is_answered": True,
                        "answer_count": 3,
                        "tags": ["python", "asyncio"],
                    }
                ]
            },
        )
    )
    respx_mock.get(GITHUB).mock(
        return_value=httpx.Response(
            200,
            json={
                "items": [
                    {
                        "full_name": "python/cpython",
                        "html_url": "https://github.com/python/cpython",
                        "description": "The Python programming language",
                        "stargazers_count": 60000,
                        "language": "Python",
                    }
                ]
            },
        )
    )
    resp = client.get("/v1/concepts/asyncio/examples", headers=auth)
    assert resp.status_code == 200, resp.json
    data = resp.json["data"]
    assert data["questions"][0]["title"] == "How to use asyncio?"
    assert data["repositories"][0]["name"] == "python/cpython"
    names = {s["name"] for s in resp.json["sources"]}
    assert {"stackexchange", "github"} <= names
    assert resp.json["degraded"] is False


def test_security_vulnerabilities_via_nvd(client, auth, respx_mock):
    respx_mock.get(NVD).mock(
        return_value=httpx.Response(
            200,
            json={
                "totalResults": 1,
                "vulnerabilities": [
                    {
                        "cve": {
                            "id": "CVE-2022-0001",
                            "descriptions": [{"lang": "en", "value": "A flaw in openssl."}],
                            "published": "2022-01-01T00:00:00",
                            "metrics": {
                                "cvssMetricV31": [
                                    {"cvssData": {"version": "3.1", "baseScore": 7.5,
                                                  "baseSeverity": "HIGH"}}
                                ]
                            },
                            "references": [{"url": "https://example/ref"}],
                        }
                    }
                ],
            },
        )
    )
    resp = client.get("/v1/security/vulnerabilities?product=openssl", headers=auth)
    assert resp.status_code == 200, resp.json
    cves = resp.json["data"]["cves"]
    assert cves[0]["id"] == "CVE-2022-0001"
    assert cves[0]["cvss"]["severity"] == "HIGH"
    assert cves[0]["cvss"]["base_score"] == 7.5


def test_academic_papers_via_arxiv(client, auth, respx_mock):
    respx_mock.get(ARXIV).mock(return_value=httpx.Response(200, text=ARXIV_XML))

    resp = client.get("/v1/academic/papers?query=transformers", headers=auth)
    assert resp.status_code == 200, resp.json
    papers = resp.json["data"]["papers"]
    assert papers[0]["title"] == "A Study of Transformers"
    assert papers[0]["authors"] == ["Jane Doe", "John Roe"]
    assert any(s["name"] == "arxiv" for s in resp.json["sources"])


def test_security_techniques_via_mitre(client, auth, respx_mock):
    respx_mock.get(MITRE).mock(
        return_value=httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "type": "attack-pattern",
                        "name": "Phishing",
                        "description": "Adversaries may send phishing messages to gain access.",
                        "external_references": [
                            {
                                "source_name": "mitre-attack",
                                "external_id": "T1566",
                                "url": "https://attack.mitre.org/techniques/T1566",
                            }
                        ],
                        "kill_chain_phases": [
                            {"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}
                        ],
                    },
                    {"type": "x-mitre-tactic", "name": "Initial Access"},
                ]
            },
        )
    )
    resp = client.get("/v1/security/techniques?query=phishing", headers=auth)
    assert resp.status_code == 200, resp.json
    techniques = resp.json["data"]["techniques"]
    assert techniques[0]["id"] == "T1566"
    assert "initial-access" in techniques[0]["tactics"]
    assert any(s["name"] == "mitre_attack" for s in resp.json["sources"])


def test_vulnerabilities_requires_product_param(client, auth):
    resp = client.get("/v1/security/vulnerabilities", headers=auth)
    assert resp.status_code == 422
