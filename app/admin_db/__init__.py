from app.admin_db import session as _session

__all__ = ["AdminSessionLocal", "admin_engine", "engine", "get_admin_db", "init_admin_db"]


def __getattr__(name: str):
    if name in __all__:
        return getattr(_session, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
