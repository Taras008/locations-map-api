from django.db import models

from common.models import SoftDeleteModel, TimeStampedModel


class Note(TimeStampedModel, SoftDeleteModel):
    title = models.CharField(max_length=50)

    class Meta:
        app_label = "common"
        managed = False  # таблицю створює фікстура, а не migrate/syncdb
