"""The ``python -m leadgen.auth`` CLI: bootstrap, listing, recovery and disabling."""

import re

import pytest
from sqlalchemy import select

from leadgen.auth import cli, recovery
from leadgen.auth.service import AuthService, RequestContext
from leadgen.db import migrate, repositories as repo
from leadgen.db.models import AuthSession
from leadgen.db.session import session_scope

CTX = RequestContext(user_agent="cli-test")


def _extract(report: str, label: str) -> str:
    match = re.search(rf"{label}\s*:\s*(\S+)", report)
    assert match is not None, report
    return match.group(1)


@pytest.fixture
def cli_env(isolated_var, api_state_reset):
    """The CLI works on the temp var dir; migrate once so commands are fast."""
    migrate.upgrade_database()
    return isolated_var


def test_list_users_on_a_fresh_database(cli_env, capsys):
    assert cli.main(["list-users"]) == 0

    assert "No users yet" in capsys.readouterr().out


def test_create_admin_prints_credentials_that_work(cli_env, capsys):
    assert cli.main(["create-admin", "boss"]) == 0

    report = capsys.readouterr().out
    password = _extract(report, "temporary password")
    code = _extract(report, "recovery code")

    assert "Created administrator 'boss'" in report
    assert recovery.is_well_formed(code) is True

    with session_scope() as db:
        service = AuthService(db)
        assert service.needs_setup() is False
        grant = service.login("boss", password, CTX)
        assert grant.user.role == "admin"
        assert grant.user.must_change_password is True


def test_create_admin_can_run_twice(cli_env, capsys):
    assert cli.main(["create-admin", "boss"]) == 0
    assert cli.main(["create-admin", "second"]) == 0
    capsys.readouterr()

    assert cli.main(["list-users"]) == 0

    report = capsys.readouterr().out
    assert "boss" in report
    assert "second" in report
    assert report.count("admin") >= 2


def test_list_users_reports_a_table(cli_env, capsys):
    cli.main(["create-admin", "boss"])
    capsys.readouterr()

    assert cli.main(["list-users"]) == 0

    report = capsys.readouterr().out
    assert "USERNAME" in report
    assert "MUST CHANGE" in report
    assert "never" in report


def test_reset_password_issues_a_working_temporary_password(cli_env, capsys):
    cli.main(["create-admin", "boss"])
    first = capsys.readouterr().out
    old_code = _extract(first, "recovery code")

    assert cli.main(["reset-password", "BOSS"]) == 0

    report = capsys.readouterr().out
    password = _extract(report, "temporary password")
    new_code = _extract(report, "recovery code")

    assert new_code != old_code
    with session_scope() as db:
        service = AuthService(db)
        grant = service.login("boss", password, CTX)
        assert grant.user.must_change_password is True


def test_reset_password_rejects_an_unknown_user(cli_env, capsys):
    migrate.upgrade_database()

    assert cli.main(["reset-password", "ghost"]) == 1

    assert "No such user" in capsys.readouterr().err


def test_disable_user_deactivates_and_revokes_sessions(cli_env, capsys):
    cli.main(["create-admin", "boss"])
    report = capsys.readouterr().out
    password = _extract(report, "temporary password")
    with session_scope() as db:
        AuthService(db).login("boss", password, CTX)

    assert cli.main(["disable-user", "boss"]) == 0

    assert "Disabled 'boss'" in capsys.readouterr().out
    with session_scope() as db:
        user = repo.users.get_by_normalized_username(db, "boss")
        assert user.is_active is False
        assert [row.revoked_reason for row in db.scalars(select(AuthSession)).all()] == ["admin"]


def test_disable_user_rejects_an_unknown_user(cli_env, capsys):
    migrate.upgrade_database()

    assert cli.main(["disable-user", "ghost"]) == 1

    assert "No such user" in capsys.readouterr().err


def test_unknown_command_exits_with_an_argparse_error(cli_env):
    with pytest.raises(SystemExit):
        cli.main(["nonsense"])

    with pytest.raises(SystemExit):
        cli.main([])
