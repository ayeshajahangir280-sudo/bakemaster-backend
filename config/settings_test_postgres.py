"""PostgreSQL-only test settings. Never accepts a non-test database."""
import os
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured

test_database_url = os.environ.get("TEST_DATABASE_URL")

if not test_database_url:
    raise ImproperlyConfigured("TEST_DATABASE_URL is required.")

parsed = urlparse(test_database_url)

if parsed.scheme not in {"postgres", "postgresql"}:
    raise ImproperlyConfigured("TEST_DATABASE_URL must use PostgreSQL.")

database_name = parsed.path.lstrip("/")

if "test" not in database_name.lower():
    raise ImproperlyConfigured(
        "TEST_DATABASE_URL must reference an explicitly named test database."
    )

os.environ["DATABASE_URL"] = test_database_url

from .settings import *  # noqa: E402,F403

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

DATABASES={"default":dj_database_url.parse(test_database_url,conn_max_age=0,conn_health_checks=True)}  # noqa: F405
# Django normally prefixes test databases. Use an explicit, still unmistakably
# test-only name so concurrent test workers never touch the configured database.
DATABASES["default"]["TEST"]={"NAME":f"test_{database_name}" if not database_name.startswith("test_") else database_name}
