from django.db import models, transaction
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """
    Масові delete()/restore() ідуть по об'єктах, а не через update(): так спрацьовують
    save() і post_save-сигнали (інвалідація кешу), а Django Admin не видаляє рядки фізично.
    """

    def alive(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)

    @transaction.atomic
    def delete(self):
        objects = list(self.alive())
        for obj in objects:
            obj.delete()
        return len(objects), {self.model._meta.label: len(objects)}

    delete.queryset_only = True

    @transaction.atomic
    def restore(self) -> int:
        objects = list(self.deleted())
        for obj in objects:
            obj.restore()
        return len(objects)

    restore.queryset_only = True

    def hard_delete(self):
        return super().delete()

    hard_delete.queryset_only = True


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Менеджер за замовчуванням: ховає м'яко видалені записи."""

    def get_queryset(self):
        return super().get_queryset().alive()


class SoftDeleteModel(models.Model):
    """
    delete() не видаляє рядок, а позначає його видаленим через save(),
    тож post_save-сигнали (інвалідація кешу) спрацьовують як для звичайної зміни.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager.from_queryset(SoftDeleteQuerySet)()

    class Meta:
        abstract = True

    def _save_soft_delete_state(self, using=None) -> None:
        update_fields = ["is_deleted", "deleted_at"]
        # auto_now оновлюється лише для полів з update_fields.
        if any(field.name == "updated_at" for field in self._meta.concrete_fields):
            update_fields.append("updated_at")
        self.save(using=using, update_fields=update_fields)

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self._save_soft_delete_state(using=using)
        return 1, {self._meta.label: 1}

    def restore(self) -> None:
        self.is_deleted = False
        self.deleted_at = None
        self._save_soft_delete_state()

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)
