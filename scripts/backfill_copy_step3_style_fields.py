from __future__ import annotations

from app.db.session import SessionLocal
from app.models.session import SessionModel
from app.services.copy_normalization import normalize_copy_payload
from app.services.parameter_snapshot import merge_parameter_snapshot_into_copy


def main() -> None:
    updated = 0
    with SessionLocal() as db:
        sessions = db.query(SessionModel).all()
        for session in sessions:
            if not session.confirmed_copy and not session.parameter_snapshot:
                continue
            original = session.confirmed_copy or {}
            normalized = normalize_copy_payload(original)
            merged = merge_parameter_snapshot_into_copy(normalized, session.parameter_snapshot)
            if merged != original:
                session.confirmed_copy = merged
                updated += 1
        db.commit()
    print(f"backfilled_sessions={updated}")


if __name__ == "__main__":
    main()
