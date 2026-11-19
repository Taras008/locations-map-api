from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/api/schema/", "/api/docs/"])
def test_api_docs_are_available(api_client, url):
    assert api_client.get(url).status_code == 200


def test_schema_has_no_warnings():
    # --fail-on-warn: нерозпізнані серіалізатори/автентифікатори ламають тест.
    call_command("spectacular", "--validate", "--fail-on-warn", stdout=StringIO())
