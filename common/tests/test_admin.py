import pytest
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from apps.users.tests.factories import UserFactory
from common.admin import SoftDeleteAdminMixin
from common.tests.models import Note


class NoteAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    ordering = ("pk",)


@pytest.fixture
def model_admin():
    return NoteAdmin(Note, AdminSite())


@pytest.fixture
def admin_request(db):
    request = RequestFactory().post("/admin/common/note/")
    request.user = UserFactory(is_staff=True, is_superuser=True)
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def test_physical_delete_action_is_replaced(model_admin, admin_request):
    actions = model_admin.get_actions(admin_request)

    assert "delete_selected" not in actions
    assert {"soft_delete_selected", "restore_selected"} <= set(actions)


def test_queryset_includes_deleted(model_admin, admin_request, note_table):
    alive = Note.objects.create(title="alive")
    deleted = Note.objects.create(title="deleted")
    deleted.delete()

    assert list(model_admin.get_queryset(admin_request)) == [alive, deleted]


def test_soft_delete_and_restore_actions(model_admin, admin_request, note_table):
    note = Note.objects.create(title="a")
    queryset = Note.all_objects.filter(pk=note.pk)

    model_admin.soft_delete_selected(admin_request, queryset)
    assert Note.all_objects.get(pk=note.pk).is_deleted
    assert not Note.objects.exists()

    model_admin.restore_selected(admin_request, queryset)
    assert Note.objects.filter(pk=note.pk).exists()

    messages = [str(m) for m in admin_request._messages]
    assert messages == ["Видалено: 1.", "Відновлено: 1."]
