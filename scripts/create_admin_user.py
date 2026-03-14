from __future__ import annotations

import argparse

from app.admin_db.session import AdminSessionLocal, init_admin_db
from app.admin_models.admin_user import AdminUserModel
from app.core.admin_auth import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update an admin user.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--display-name", default="Admin")
    args = parser.parse_args()

    init_admin_db()
    with AdminSessionLocal() as db:
        user = db.query(AdminUserModel).filter(AdminUserModel.username == args.username).one_or_none()
        if user is None:
            user = AdminUserModel(
                username=args.username,
                password_hash=hash_password(args.password),
                display_name=args.display_name,
                is_active=True,
            )
            db.add(user)
        else:
            user.password_hash = hash_password(args.password)
            user.display_name = args.display_name
            user.is_active = True
        db.commit()
        print(user.id)


if __name__ == "__main__":
    main()
