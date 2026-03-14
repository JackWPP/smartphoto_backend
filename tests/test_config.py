from app.core import config as config_module


def test_resolve_database_url_uses_available_psycopg(monkeypatch):
    def fake_module_exists(name: str) -> bool:
        return name == "psycopg"

    monkeypatch.setattr(config_module, "_module_exists", fake_module_exists)
    resolved = config_module.resolve_database_url("postgresql://smartphoto:smartphoto@localhost:5432/smartphoto")
    assert resolved == "postgresql+psycopg://smartphoto:smartphoto@localhost:5432/smartphoto"


def test_resolve_database_url_switches_to_psycopg2_when_needed(monkeypatch):
    def fake_module_exists(name: str) -> bool:
        return name == "psycopg2"

    monkeypatch.setattr(config_module, "_module_exists", fake_module_exists)
    resolved = config_module.resolve_database_url("postgresql+psycopg://smartphoto:smartphoto@localhost:5432/smartphoto")
    assert resolved == "postgresql+psycopg2://smartphoto:smartphoto@localhost:5432/smartphoto"
