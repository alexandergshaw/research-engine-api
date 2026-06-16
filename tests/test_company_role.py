import httpx

TICKERS = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0000320193.json"
WIKIDATA = "https://www.wikidata.org/w/api.php"
ESCO_SEARCH = "https://ec.europa.eu/esco/api/search"
ESCO_RESOURCE = "https://ec.europa.eu/esco/api/resource/occupation"


def test_company_profile_via_sec_edgar(client, auth, respx_mock):
    respx_mock.get(TICKERS).mock(
        return_value=httpx.Response(
            200,
            json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}},
        )
    )
    respx_mock.get(SUBMISSIONS).mock(
        return_value=httpx.Response(
            200,
            json={
                "name": "Apple Inc.",
                "sicDescription": "Electronic Computers",
                "sic": "3571",
                "entityType": "operating",
                "fiscalYearEnd": "0928",
                "stateOfIncorporation": "CA",
                "exchanges": ["Nasdaq"],
                "addresses": {
                    "business": {
                        "street1": "One Apple Park Way",
                        "city": "Cupertino",
                        "stateOrCountry": "CA",
                        "zipCode": "95014",
                    }
                },
            },
        )
    )
    respx_mock.get(WIKIDATA).mock(return_value=httpx.Response(200, json={"search": []}))

    resp = client.get("/v1/companies/AAPL/profile", headers=auth)
    assert resp.status_code == 200, resp.json
    data = resp.json["data"]
    assert data["name"] == "Apple Inc."
    assert data["cik"] == "0000320193"
    assert data["industry"] == "Electronic Computers"
    assert data["headquarters"]["city"] == "Cupertino"
    assert any(s["name"] == "sec_edgar" for s in resp.json["sources"])
    assert resp.json["degraded"] is False


def test_company_profile_prefers_sec_and_keeps_only_wikidata_facts(client, auth, respx_mock):
    respx_mock.get(TICKERS).mock(
        return_value=httpx.Response(
            200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
        )
    )
    respx_mock.get(SUBMISSIONS).mock(
        return_value=httpx.Response(
            200, json={"name": "Apple Inc.", "sicDescription": "Electronic Computers"}
        )
    )

    def wikidata_router(request):
        if request.url.params.get("action") == "wbsearchentities":
            return httpx.Response(200, json={"search": [{"id": "Q12345"}]})
        return httpx.Response(
            200,
            json={
                "entities": {
                    "Q12345": {
                        "labels": {"en": {"value": "Apple Records"}},
                        "descriptions": {"en": {"value": "record label"}},
                        "aliases": {},
                        "claims": {
                            "P571": [
                                {
                                    "mainsnak": {
                                        "datavalue": {"value": {"time": "+1968-01-01T00:00:00Z"}}
                                    }
                                }
                            ]
                        },
                    }
                }
            },
        )

    respx_mock.get(WIKIDATA).mock(side_effect=wikidata_router)

    resp = client.get("/v1/companies/AAPL/profile", headers=auth)
    assert resp.status_code == 200, resp.json
    data = resp.json["data"]
    assert data["name"] == "Apple Inc."  # SEC wins
    assert "label" not in data  # Wikidata's mismatched label is dropped
    assert data["facts"]["inception"].startswith("1968")  # but its facts are kept


def test_role_responsibilities_via_esco(client, auth, respx_mock):
    respx_mock.get(ESCO_SEARCH).mock(
        return_value=httpx.Response(
            200,
            json={
                "_embedded": {
                    "results": [
                        {
                            "title": "software developer",
                            "uri": "http://data.europa.eu/esco/occupation/abc",
                            "_links": {
                                "self": {"href": f"{ESCO_RESOURCE}?uri=abc&language=en"}
                            },
                        }
                    ]
                }
            },
        )
    )
    respx_mock.get(ESCO_RESOURCE).mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "software developer",
                "uri": "http://data.europa.eu/esco/occupation/abc",
                "description": {"en": {"literal": "Software developers create software."}},
                "_links": {
                    "hasEssentialSkill": [
                        {"title": "use programming languages"},
                        {"title": "debug software"},
                    ],
                    "hasOptionalSkill": [{"title": "use Git"}],
                },
            },
        )
    )

    resp = client.get("/v1/roles/developer/responsibilities", headers=auth)
    assert resp.status_code == 200, resp.json
    data = resp.json["data"]
    assert data["title"] == "software developer"
    assert data["description"] == "Software developers create software."
    assert "use programming languages" in data["essential_skills"]
    assert "use Git" in data["optional_skills"]
    assert any(s["name"] == "esco" for s in resp.json["sources"])
