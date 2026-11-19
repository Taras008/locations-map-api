#!/bin/sh
set -eu

python manage.py wait_for_db --timeout "${DB_WAIT_TIMEOUT:-60}"

# Міграції та статику виконує лише web-контейнер (RUN_MIGRATIONS=1), worker тільки чекає БД.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

exec "$@"
