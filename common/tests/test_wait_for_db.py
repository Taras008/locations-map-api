from io import StringIO
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.db.utils import OperationalError

TARGET = "common.management.commands.wait_for_db.connection.ensure_connection"


def test_wait_for_db_retries_until_available():
    out = StringIO()
    with mock.patch(TARGET, side_effect=[OperationalError, None]) as ensure:
        call_command("wait_for_db", interval=0, stdout=out)

    assert ensure.call_count == 2
    assert "Database is available" in out.getvalue()


def test_wait_for_db_fails_after_timeout():
    with mock.patch(TARGET, side_effect=OperationalError), pytest.raises(CommandError):
        call_command("wait_for_db", timeout=0, interval=0, stdout=StringIO())
