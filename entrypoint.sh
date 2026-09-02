#!/bin/sh
set -e

python manage.py check --deploy
python manage.py migrate --noinput
case "${CREATE_TEST_ACCOUNT:-false}" in
    true|TRUE|True|1|yes|YES|on|ON) python manage.py ensure_test_account ;;
esac
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
