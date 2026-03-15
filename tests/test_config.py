from app.core import config as config_module
from app.services import storage as storage_module


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


def test_normalize_rel_key_accepts_virtual_and_path_style_s3_urls(monkeypatch):
    config_module.get_settings.cache_clear()
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "smartphoto-1328781951")
    virtual_url = (
        "https://smartphoto-1328781951.cos.ap-beijing.myqcloud.com/"
        "uploads/sessions/demo/session_image/example.jpg"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=test"
    )
    path_style_url = (
        "https://cos.ap-beijing.myqcloud.com/smartphoto-1328781951/"
        "uploads/sessions/demo/session_image/example.jpg"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Signature=test"
    )

    expected = "uploads/sessions/demo/session_image/example.jpg"
    assert storage_module._normalize_rel_key("/storage/uploads/sessions/demo/session_image/example.jpg") == expected
    assert storage_module._normalize_rel_key(virtual_url) == expected
    assert storage_module._normalize_rel_key(path_style_url) == expected
    config_module.get_settings.cache_clear()
