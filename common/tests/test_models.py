"""SoftDeleteModel перевіряється на тестовій моделі Note (таблицю створює фікстура note_table)."""

from datetime import timedelta

import pytest
from django.db.models.signals import post_save
from freezegun import freeze_time

from common.tests.models import Note


@pytest.mark.django_db
def test_soft_delete_hides_from_default_manager(note_table):
    note = Note.objects.create(title="a")

    note.delete()

    assert not Note.objects.filter(pk=note.pk).exists()
    deleted = Note.all_objects.get(pk=note.pk)
    assert deleted.is_deleted
    assert deleted.deleted_at is not None
    assert list(Note.all_objects.deleted()) == [deleted]


@pytest.mark.django_db
def test_restore(note_table):
    note = Note.objects.create(title="a")
    note.delete()

    note.restore()

    assert Note.objects.filter(pk=note.pk).exists()
    assert Note.all_objects.get(pk=note.pk).deleted_at is None


@pytest.mark.django_db
def test_hard_delete_removes_row(note_table):
    note = Note.objects.create(title="a")

    note.hard_delete()

    assert not Note.all_objects.filter(pk=note.pk).exists()


@pytest.mark.django_db
def test_soft_delete_and_restore_update_updated_at(note_table):
    with freeze_time("2026-01-01"):
        note = Note.objects.create(title="a")
    created = note.updated_at

    with freeze_time("2026-01-02"):
        note.delete()
    assert note.updated_at == created + timedelta(days=1)

    with freeze_time("2026-01-03"):
        note.restore()
    assert note.updated_at == created + timedelta(days=2)


@pytest.fixture
def saved_notes():
    saved = []

    def receiver(sender, instance, **kwargs):
        saved.append(instance.pk)

    post_save.connect(receiver, sender=Note)
    yield saved
    post_save.disconnect(receiver, sender=Note)


@pytest.mark.django_db
def test_queryset_delete_is_soft_and_sends_signals(note_table, saved_notes):
    notes = [Note.objects.create(title=str(i)) for i in range(3)]
    saved_notes.clear()

    count, per_model = Note.objects.filter(pk__in=[n.pk for n in notes[:2]]).delete()

    assert count == 2
    assert per_model == {"common.Note": 2}
    assert sorted(saved_notes) == sorted(n.pk for n in notes[:2])
    assert Note.all_objects.count() == 3  # рядки лишилися в БД
    assert list(Note.objects.values_list("pk", flat=True)) == [notes[2].pk]


@pytest.mark.django_db
def test_queryset_delete_skips_already_deleted(note_table, saved_notes):
    note = Note.objects.create(title="a")
    note.delete()
    saved_notes.clear()

    count, _ = Note.all_objects.all().delete()

    assert count == 0
    assert saved_notes == []


@pytest.mark.django_db
def test_queryset_restore_sends_signals(note_table, saved_notes):
    notes = [Note.objects.create(title=str(i)) for i in range(2)]
    Note.objects.all().delete()
    saved_notes.clear()

    restored = Note.all_objects.all().restore()

    assert restored == 2
    assert sorted(saved_notes) == sorted(n.pk for n in notes)
    assert Note.objects.count() == 2


@pytest.mark.django_db
def test_queryset_hard_delete_removes_rows(note_table):
    Note.objects.create(title="a")

    Note.all_objects.all().hard_delete()

    assert Note.all_objects.count() == 0
