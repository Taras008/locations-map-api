import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.utils import OperationalError


class Command(BaseCommand):
    help = "Чекає, доки база даних почне приймати з'єднання."

    def add_arguments(self, parser):
        parser.add_argument("--timeout", type=int, default=60, help="Максимум секунд очікування")
        parser.add_argument("--interval", type=float, default=1.0)

    def handle(self, *args, timeout: int, interval: float, **options):
        deadline = time.monotonic() + timeout
        while True:
            try:
                connection.ensure_connection()
            except OperationalError as exc:
                if time.monotonic() >= deadline:
                    raise CommandError(f"Database unavailable after {timeout}s: {exc}") from exc
                self.stdout.write("Waiting for database...")
                time.sleep(interval)
            else:
                self.stdout.write(self.style.SUCCESS("Database is available"))
                return
