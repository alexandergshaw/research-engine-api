from app import create_app
from app.config import TestConfig


class LimitedConfig(TestConfig):
    RATELIMIT_ENABLED = True
    RATELIMIT_DEFAULT = "2/minute"
    RATELIMIT_STORAGE_URI = "memory://"


def test_per_key_rate_limit_enforced():
    app = create_app(LimitedConfig)
    headers = {"X-API-Key": "test-key"}
    with app.app_context():
        client = app.test_client()
        # /v1/intents needs no upstream, so this isolates the limiter.
        statuses = [client.get("/v1/intents", headers=headers).status_code for _ in range(3)]

    assert statuses[0] == 200
    assert statuses[1] == 200
    assert statuses[2] == 429
