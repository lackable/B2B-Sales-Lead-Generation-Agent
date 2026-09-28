"""``python -m leadgen.auth <command>`` — bootstrap and account recovery without the UI.

Commands::

    create-admin <username>     create an administrator (first user allowed)
    reset-password <username>   issue a temporary password + new recovery code
    list-users                  show every account
    disable-user <username>     disable an account and revoke its sessions
"""

import argparse
import sys
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from leadgen import config
from leadgen.auth.errors import AuthError
from leadgen.auth.service import AuthService, RequestContext, normalize_username
from leadgen.db import migrate, repositories as repo
from leadgen.db.models import ROLE_ADMIN, User
from leadgen.db.session import session_scope

CLI_CONTEXT = RequestContext(ip_address=None, user_agent="leadgen-auth-cli")


def _print_credentials(username: str, password: str, recovery_code: str) -> None:
    print()
    print(f"  username           : {username}")
    print(f"  temporary password : {password}")
    print(f"  recovery code      : {recovery_code}")
    print()
    print("  The password must be changed at first login.")
    print("  The recovery code is shown once — store it somewhere safe.")


def _find_user(db: Session, username: str) -> Optional[User]:
    return repo.users.get_by_normalized_username(db, normalize_username(username))


def _create_admin(args: argparse.Namespace) -> int:
    with session_scope() as db:
        created = AuthService(db).create_user(username=args.username, role=ROLE_ADMIN, ctx=CLI_CONTEXT)

    print(f"Created administrator '{created.user.username}'.")
    _print_credentials(created.user.username, created.temporary_password, created.recovery_code)
    return 0


def _reset_password(args: argparse.Namespace) -> int:
    with session_scope() as db:
        user = _find_user(db, args.username)
        if user is None:
            print(f"No such user: {args.username}", file=sys.stderr)
            return 1
        password, code = AuthService(db).admin_reset_password(user, ctx=CLI_CONTEXT)
        username = user.username

    print(f"Reset the password of '{username}' and revoked its sessions.")
    _print_credentials(username, password, code)
    return 0


def _list_users(_args: argparse.Namespace) -> int:
    with session_scope() as db:
        users = list(AuthService(db).list_users())

    if not users:
        print("No users yet. Run: python -m leadgen.auth create-admin <username>")
        return 0

    print(f"{'USERNAME':<24}{'ROLE':<8}{'ACTIVE':<8}{'MUST CHANGE':<13}{'LAST LOGIN':<21}CREATED")
    for user in users:
        last_login = user.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if user.last_login_at else "never"
        print(
            f"{user.username:<24}{user.role:<8}{str(user.is_active):<8}"
            f"{str(user.must_change_password):<13}{last_login:<21}"
            f"{user.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    return 0


def _disable_user(args: argparse.Namespace) -> int:
    with session_scope() as db:
        user = _find_user(db, args.username)
        if user is None:
            print(f"No such user: {args.username}", file=sys.stderr)
            return 1
        service = AuthService(db)
        service.update_user(user_id=user.id, is_active=False, ctx=CLI_CONTEXT)

    print(f"Disabled '{args.username}' and revoked its sessions.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m leadgen.auth", description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser("create-admin", help="create an administrator account")
    create_admin.add_argument("username")
    create_admin.set_defaults(func=_create_admin)

    reset_password = subparsers.add_parser("reset-password", help="issue a temporary password and recovery code")
    reset_password.add_argument("username")
    reset_password.set_defaults(func=_reset_password)

    list_users = subparsers.add_parser("list-users", help="list every account")
    list_users.set_defaults(func=_list_users)

    disable_user = subparsers.add_parser("disable-user", help="disable an account and revoke its sessions")
    disable_user.add_argument("username")
    disable_user.set_defaults(func=_disable_user)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run one CLI command; returns a process exit code."""
    args = build_parser().parse_args(argv)
    config.ensure_runtime_dirs()
    migrate.upgrade_database()

    try:
        return int(args.func(args))
    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1
