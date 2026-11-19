"""
Кеш відповіді списку локацій.

Ключ — `locations:list:v{version}:{sha1(параметрів)}`. Інвалідація не шукає ключі, а
інкрементує версію: старі записи стають недосяжними й вичищаються за TTL. Будь-яка помилка
Redis — це промах кешу, а не помилка запиту.
"""

import hashlib
import logging
import time
from collections.abc import Iterable

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.http import QueryDict

logger = logging.getLogger(__name__)

VERSION_KEY = "locations:list:version"


def _new_version() -> int:
    # Унікальне значення замість 1: якщо ключ версії витіснили, ми не повернемося
    # до версії, під якою ще лежать старі записи.
    return time.time_ns()


def _get_version() -> int:
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.add(VERSION_KEY, _new_version(), None)
        version = cache.get(VERSION_KEY)
    if version is None:
        raise ConnectionError("List cache version is unavailable")
    return version


def list_cache_key(query_params: QueryDict, known_params: Iterable[str]) -> str:
    """
    Лише відомі параметри, відсортовані за назвою: `?foo=1` не плодить записів, а
    `?a=1&b=2` і `?b=2&a=1` дають один ключ. Порядок значень одного параметра зберігається.
    """
    known = set(known_params)
    items = sorted((name, values) for name, values in query_params.lists() if name in known)
    params = QueryDict(mutable=True)
    for name, values in items:
        params.setlist(name, values)
    digest = hashlib.sha1(params.urlencode().encode(), usedforsecurity=False).hexdigest()
    return f"locations:list:v{_get_version()}:{digest}"


def get_cached_list(
    query_params: QueryDict, known_params: Iterable[str]
) -> tuple[str | None, object]:
    """Повертає (ключ, дані); ключ None — кеш недоступний, дані None — промах."""
    try:
        key = list_cache_key(query_params, known_params)
        return key, cache.get(key)
    except Exception:
        # Другий рубіж: зазвичай помилки Redis гасить IGNORE_EXCEPTIONS.
        logger.warning("Location list cache unavailable", exc_info=True)
        return None, None


def set_cached_list(key: str, data) -> None:
    try:
        cache.set(key, data, settings.LOCATIONS_LIST_CACHE_TTL)
    except Exception:
        logger.warning("Location list cache unavailable", exc_info=True)


def _bump_version() -> None:
    try:
        try:
            cache.incr(VERSION_KEY)
        except ValueError:
            # Ключа версії немає (перший запуск або витіснення).
            cache.set(VERSION_KEY, _new_version(), None)
    except Exception:
        logger.warning("Location list cache invalidation failed", exc_info=True)


def invalidate_list_cache() -> None:
    """
    Скидає кеш одразу і ще раз після коміту: інакше паралельний запит між зміною й комітом
    прочитає старі дані з БД і закешує їх уже під новою версією.
    """
    _bump_version()
    transaction.on_commit(_bump_version)
