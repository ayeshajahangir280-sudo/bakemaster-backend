# PostgreSQL test environment

`erp-erp-mscnom` is present only in the local `.env`. The repository's production Compose file does not define PostgreSQL, and the deployment guide describes `DATABASE_URL` as an external Dokploy resource. The hostname is therefore treated as deployment-network-only or stale; it is not replaced automatically.

Concurrency tests must use `config.settings_test_postgres`. This settings module reads only `TEST_DATABASE_URL`, requires PostgreSQL, and refuses database names that do not contain `test`. It never silently falls back to SQLite.

With Docker installed:

```powershell
docker compose -f docker-compose.test.yml up -d --wait
$env:TEST_DATABASE_URL='postgresql://bakeryflow_test:bakeryflow_test_local_only@127.0.0.1:55432/bakeryflow_test'
python manage.py test tests.postgres --settings=config.settings_test_postgres
docker compose -f docker-compose.test.yml down
```

The test service binds only to loopback and stores data in tmpfs. Its credentials are local test defaults, not production secrets. For an existing test server, set `TEST_DATABASE_URL` to a dedicated disposable database whose name contains `test`.

Quick unit tests may explicitly use SQLite by setting `DATABASE_URL=sqlite:///...`; their results are not evidence of PostgreSQL locking behavior.
