import httpx
import respx

from app import create_app
from app.auth.models import ApiKey, Tenant
from app.config import TestConfig
from app.extensions import db

WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary/RSA"
WIKIDATA = "https://www.wikidata.org/w/api.php"


class LimitedConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"


def test_per_tenant_rate_limit_enforced():
    app = create_app(LimitedConfig)
    with app.app_context():
        db.create_all()
        tenant = Tenant(name="rl-tenant", rate_limit="2/minute")
        db.session.add(tenant)
        db.session.flush()
        key, raw = ApiKey.generate(tenant)
        db.session.add(key)
        db.session.commit()

        client = app.test_client()
        headers = {"X-API-Key": raw}
        with respx.mock(assert_all_called=False) as mock:
            mock.get(WIKI).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "title": "RSA",
                        "extract": "x",
                        "content_urls": {"desktop": {"page": "u"}},
                    },
                )
            )
            mock.get(WIKIDATA).mock(return_value=httpx.Response(200, json={"search": []}))

            statuses = [
                client.get("/v1/concepts/RSA/overview", headers=headers).status_code
                for _ in range(3)
            ]

        db.session.remove()
        db.drop_all()

    assert statuses[0] == 200
    assert statuses[1] == 200
    assert statuses[2] == 429
