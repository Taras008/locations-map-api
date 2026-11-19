import json
import logging
import sys

from common.logging import JsonFormatter


def make_record(**extra) -> logging.LogRecord:
    record = logging.makeLogRecord(
        {"name": "app", "levelname": "INFO", "msg": "Відгук %s", "args": (7,), **extra}
    )
    return record


def test_json_formatter_outputs_one_json_object_with_extra_fields():
    line = JsonFormatter().format(make_record(review_id=7))

    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app"
    assert payload["message"] == "Відгук 7"
    assert payload["review_id"] == 7
    assert "timestamp" in payload


def test_json_formatter_includes_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record(exc_info=sys.exc_info())

    payload = json.loads(JsonFormatter().format(record))

    assert "ValueError: boom" in payload["exc_info"]
