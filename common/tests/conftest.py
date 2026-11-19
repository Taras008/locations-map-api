import pytest
from django.db import connection

from common.tests.models import Note


@pytest.fixture
def note_table(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        with connection.schema_editor() as editor:
            editor.create_model(Note)
        yield
        with connection.schema_editor() as editor:
            editor.delete_model(Note)
