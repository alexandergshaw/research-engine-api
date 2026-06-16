import importlib


def test_prod_config_selects_redis_and_postgres(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h:5432/db")

    import app.config as cfg

    importlib.reload(cfg)
    try:
        assert cfg.Config.CACHE_TYPE == "RedisCache"
        assert cfg.Config.CACHE_REDIS_URL == "redis://cache:6379/0"
        assert cfg.Config.RATELIMIT_STORAGE_URI == "redis://cache:6379/0"
        assert cfg.Config.SQLALCHEMY_DATABASE_URI.startswith("postgresql")
    finally:
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        importlib.reload(cfg)  # restore default module state for other tests


def test_default_config_uses_sqlite_and_in_memory():
    import app.config as cfg

    importlib.reload(cfg)
    assert cfg.Config.CACHE_TYPE == "SimpleCache"
    assert cfg.Config.SQLALCHEMY_DATABASE_URI.startswith("sqlite")
    assert cfg.Config.RATELIMIT_STORAGE_URI == "memory://"
