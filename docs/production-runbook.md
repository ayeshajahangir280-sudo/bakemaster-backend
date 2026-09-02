# BakeryFlow production runbook

## Environments and workflows

Use separate PostgreSQL databases and secrets for CI, staging, and production. GitHub workflows use temporary service containers only and never accept production database URLs. Run `postgresql-tests.yml`, `query-plans.yml`, `backup-restore.yml`, and `load-smoke.yml` from GitHub Actions before release. The frontend repository must pass `frontend-checks.yml`.

In Dokploy, set `DATABASE_URL` to the PostgreSQL service's internal hostname, not `localhost` and not its public endpoint. Required variables are `DJANGO_SECRET_KEY`, `DATABASE_URL`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`, `TIME_ZONE`, and `REDIS_URL`. Store them in Dokploy secrets and rotate immediately after suspected exposure.

### Dokploy and Traefik HTTPS

Traefik must terminate TLS and forward `X-Forwarded-Proto: https`; Django trusts that header through `SECURE_PROXY_SSL_HEADER`. Set these production environment values in Dokploy:

```dotenv
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
```

Keep Traefik's HTTP-to-HTTPS entrypoint redirect enabled as the first line of enforcement. Django's redirect is defense in depth and will not loop when Traefik sends the forwarded-protocol header correctly.

The conservative `False` values for HSTS subdomains and preload are intentional. This deployment has no verified inventory proving that every current and future subdomain is HTTPS-only, and browser preload is long-lived and difficult to reverse. Consequently, Django deploy checks W005 and W021 are expected until domain ownership and TLS coverage are verified. Only then set `SECURE_HSTS_INCLUDE_SUBDOMAINS=True`; request preload and set `SECURE_HSTS_PRELOAD=True` only after satisfying the browser preload requirements.

Test-account provisioning is disabled by default with `CREATE_TEST_ACCOUNT=False`. Production must retain that value. For an explicitly authorized temporary test environment only, set `CREATE_TEST_ACCOUNT=True` and provide `TEST_ACCOUNT_PASSWORD` as a secret; startup and management commands never print the password.

The internal Dokploy health check may call `http://127.0.0.1:8000/api/health/`. That single path is exempt from Django's HTTPS redirect and returns only `{"status":"ok"}` when the database connection is available. All other application and API paths retain `SECURE_SSL_REDIRECT` protection.

## Deployment

1. Create and verify an off-server backup.
2. Run `python manage.py audit_payment_migration_data` and require zero blocking issues.
3. Run `python manage.py check --deploy` and `python manage.py makemigrations --check --dry-run`.
4. Drain application traffic, then run `python manage.py migrate --noinput` once.
5. Start the web process, check `/api/health/`, then perform the staging QA checklist.
6. Run inventory and financial fingerprints/reconciliation and compare dashboard totals with reports.

Use Gunicorn with bounded request timeouts and multiple workers. Gunicorn is the only continuously running application process required. Excel exports are generated synchronously and are limited by `REPORT_XLSX_MAX_ROWS` (default 10,000); users must select streaming CSV for larger exports. `REPORT_EXPORT_SPOOL_MAX_BYTES` (default 5 MiB) bounds in-memory XLSX buffering before it spills to a temporary file. Existing historical export-job records and completed downloads remain available until their recorded expiry. The legacy export processor is retained only for historical pending records and is not required for new exports. Schedule `python manage.py cleanup_report_exports` and `python manage.py cleanup_idempotency_records` as optional daily one-shot tasks. Put a connection pool such as PgBouncer in transaction mode between the application and PostgreSQL when connection concurrency requires it.

`erp-erp-mscnom` is resolvable only between services on the Dokploy internal network. A Dokploy application database URL may use `postgresql://USER:PASSWORD@erp-erp-mscnom:5432/DATABASE`; developer machines and GitHub Actions must not use that hostname. CI uses its own PostgreSQL 17 service on `127.0.0.1` with clearly test-only database names. Staging must use a separate database and credentials from production.

## Backup and restore

Take daily custom-format backups with `pg_dump -Fc`, retain daily copies for 14 days and monthly copies for 12 months, encrypt them, and copy them off-server. Test restoration monthly.

Restore only into an empty database:

```sh
createdb bakeryflow_restore
pg_restore --no-owner --exit-on-error -d bakeryflow_restore bakeryflow.dump
DATABASE_URL=postgresql://USER:PASSWORD@INTERNAL_HOST/bakeryflow_restore python manage.py check
DATABASE_URL=postgresql://USER:PASSWORD@INTERNAL_HOST/bakeryflow_restore python manage.py migrate --check
DATABASE_URL=postgresql://USER:PASSWORD@INTERNAL_HOST/bakeryflow_restore python manage.py database_fingerprint --output restored.json
```

Never place real credentials in commands committed to Git. Switch application traffic only after counts, outstanding balances, inventory values, and reconciliation match.

## Rollback

Stop new writes, retain the failed database, deploy the previous application image, and restore the pre-deployment backup when a migration changed data incompatibly. Do not blindly reverse transactional migrations after new documents have posted. Record the incident and exact recovery point.

## Monitoring and security

Monitor health checks, HTTP 5xx/409 rates, worker failures, slow queries, lock waits, database connections, replication/backup age, disk usage, memory, and reconciliation discrepancies. Alert on negative balance attempts and failed exports. Apply API rate limits at the ingress, use TLS, restrict allowed hosts/CORS/CSRF origins, use least-privilege database accounts, and rotate application/database secrets on a defined schedule.

## Staging QA and launch checklist

- Verify administrator, manager, restricted-location, and unauthorized users.
- Post and cancel purchases, production, sales, transfers/receipts, returns, wastage, adjustments, opening stock, and both payment types.
- Exercise partial/damaged receipts and partial/multi-invoice allocations.
- Verify duplicate submissions replay safely and conflicting keys return 409.
- Confirm deactivated masters disappear while historical documents and ledgers remain.
- Compare every dashboard KPI with its report and database fingerprint.
- Run PostgreSQL races, query plans, backup/restore, load smoke, and full staging load tests.
- Confirm logs contain no secrets and backups restore off-server.
