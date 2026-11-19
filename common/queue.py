import logging

from celery import Task
from django.db import transaction

logger = logging.getLogger(__name__)


def enqueue_on_commit(task: Task, *args, **kwargs) -> None:
    """
    Ставить Celery-задачу в чергу після коміту поточної транзакції.

    Поза транзакцією on_commit виконує callback одразу, тобто публікація в брокер
    відбувається всередині запиту. Недоступний брокер не повинен перетворювати
    успішну операцію на 500, тож помилку публікації лише логуємо.
    """

    def publish() -> None:
        try:
            task.delay(*args, **kwargs)
        except Exception:
            logger.exception("Failed to enqueue task", extra={"task": task.name})

    transaction.on_commit(publish)
