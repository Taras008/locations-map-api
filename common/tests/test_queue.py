import logging
from unittest import mock

import pytest
from kombu.exceptions import OperationalError

from common.queue import enqueue_on_commit

pytestmark = pytest.mark.django_db


def make_task():
    task = mock.Mock()
    task.name = "tests.task"
    return task


def test_publishes_only_after_commit(django_capture_on_commit_callbacks):
    task = make_task()

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        enqueue_on_commit(task, 1, key="value")

    task.delay.assert_not_called()
    callbacks[0]()
    task.delay.assert_called_once_with(1, key="value")


def test_broker_failure_is_logged_not_raised(django_capture_on_commit_callbacks, caplog):
    task = make_task()
    task.delay.side_effect = OperationalError("broker down")

    with (
        caplog.at_level(logging.ERROR, logger="common.queue"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        enqueue_on_commit(task)

    assert "Failed to enqueue task" in caplog.text
