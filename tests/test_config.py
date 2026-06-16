import importlib


def test_api_keys_and_disabled_connectors_parsed_from_env(monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1, k2 ,k3")
    monkeypatch.setenv("DISABLED_CONNECTORS", "mitre_attack")

    import app.config as cfg

    importlib.reload(cfg)
    try:
        assert cfg.Config.API_KEYS == frozenset({"k1", "k2", "k3"})
        assert "mitre_attack" in cfg.Config.DISABLED_CONNECTORS
    finally:
        monkeypatch.delenv("API_KEYS", raising=False)
        monkeypatch.delenv("DISABLED_CONNECTORS", raising=False)
        importlib.reload(cfg)  # restore default module state for other tests


def test_defaults_are_stateless():
    import app.config as cfg

    importlib.reload(cfg)
    assert cfg.Config.API_KEYS == frozenset()  # open by default
    assert cfg.Config.CACHE_TYPE == "SimpleCache"
    assert cfg.Config.RATELIMIT_STORAGE_URI == "memory://"
    # No database configuration anywhere.
    assert not hasattr(cfg.Config, "SQLALCHEMY_DATABASE_URI")
