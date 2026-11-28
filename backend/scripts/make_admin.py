"""Grant or revoke administrator access for an existing user.

Usage:
    uv run --project backend python backend/scripts/make_admin.py --email someone@example.com
    uv run --project backend python backend/scripts/make_admin.py --user-name alice --revoke
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.database import SessionLocal  # noqa: E402
from backend.app.models.user import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--email")
    identity.add_argument("--user-name")
    parser.add_argument("--revoke", action="store_true", help="Remove administrator access.")
    args = parser.parse_args()

    query = (
        select(User).where(func.lower(func.trim(User.email)) == args.email.strip().lower())
        if args.email
        else select(User).where(User.user_name == args.user_name.strip())
    )
    with SessionLocal() as session:
        user = session.scalar(query.with_for_update())
        if user is None:
            print("User not found.", file=sys.stderr)
            return 1
        user.is_admin = not args.revoke
        session.commit()
        state = "revoked from" if args.revoke else "granted to"
        print(f"Administrator access {state} {user.user_name} (user_id={user.user_id}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
