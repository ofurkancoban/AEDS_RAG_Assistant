"""Create or update an admin account from the command line.

Public registration is closed (see api/routes_auth.py): people using the
assistant stay anonymous and never create accounts, so the only accounts that
exist are staff ones. This script is how those are managed after the initial
bootstrap - deliberately a local command rather than an HTTP endpoint, so
there is no account-creation surface exposed to the internet at all.

    python -m scripts.create_admin someone@uol.de
    python -m scripts.create_admin someone@uol.de --demote
    python -m scripts.create_admin --list

The password is read interactively so it never lands in shell history.
"""

import argparse
import getpass
import sys

from api.auth import hash_password
from api.routes_auth import MIN_PASSWORD_LENGTH, _normalise_email
from db.models import Role, SessionLocal, User, init_db


def _list_accounts(session) -> None:
    accounts = (
        session.query(User).filter(User.is_guest.is_(False)).order_by(User.id).all()
    )
    guests = session.query(User).filter(User.is_guest.is_(True)).count()

    if not accounts:
        print("No staff accounts yet.")
    else:
        print(f"{'id':>4}  {'role':<6}  email")
        for user in accounts:
            print(f"{user.id:>4}  {user.role.value:<6}  {user.email}")
    print(f"\n({guests} anonymous session identities, not shown)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email", nargs="?", help="Address of the account to create or promote")
    parser.add_argument("--demote", action="store_true", help="Drop the account to a plain user")
    parser.add_argument("--list", action="store_true", help="Show existing staff accounts")
    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        if args.list or not args.email:
            _list_accounts(session)
            return 0 if args.list else 1

        email = _normalise_email(args.email)
        user = session.query(User).filter(User.email == email).first()

        if user is not None and user.is_guest:
            # Guests authenticate by token only and hold an unusable password
            # hash; turning one into a login would contradict that.
            print(f"{email} is an anonymous session identity, not a staff account.", file=sys.stderr)
            return 1

        if args.demote:
            if user is None:
                print(f"No account for {email}.", file=sys.stderr)
                return 1
            if session.query(User).filter(User.role == Role.ADMIN, User.is_guest.is_(False)).count() <= 1 \
                    and user.role == Role.ADMIN:
                # Otherwise the admin screens become unreachable and the only
                # way back is this same script against the database directly.
                print("Refusing to demote the last remaining admin.", file=sys.stderr)
                return 1
            user.role = Role.USER
            session.commit()
            print(f"{email} is now a plain user.")
            return 0

        password = getpass.getpass("Password: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
            return 1
        if password != getpass.getpass("Repeat password: "):
            print("Passwords do not match.", file=sys.stderr)
            return 1

        if user is None:
            session.add(
                User(
                    email=email,
                    hashed_password=hash_password(password),
                    role=Role.ADMIN,
                    is_guest=False,
                )
            )
            action = "created"
        else:
            user.hashed_password = hash_password(password)
            user.role = Role.ADMIN
            action = "updated"

        session.commit()
        print(f"Admin account {action}: {email}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
