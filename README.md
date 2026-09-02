# BakeryFlow ERP Backend

Standalone Django REST Framework backend for the existing Lovable frontend. It uses JWT authentication, explicit per-user module assignments, location-scoped data access, PostgreSQL, and an immutable stock ledger.

## Setup

Copy `.env.example` to `.env` and replace `DATABASE_URL` with the PostgreSQL URL you provide. Never commit `.env`.

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
python manage.py runserver
```

Docker: `copy .env.example .env`, then run `docker compose up --build`.

## Dokploy deployment

Use either a Dokploy **Application** with build type **Dockerfile**, or a
Dokploy **Docker Compose** service.

### Dockerfile application (recommended)

1. Connect `https://github.com/ayeshajahangir280-sudo/ERP-backend.git`, branch
   `main`.
2. Select build type **Dockerfile**, Dockerfile path `Dockerfile`, and context
   path `.`.
3. Add these service environment variables in Dokploy:

   ```env
   DJANGO_SECRET_KEY=generate-a-long-random-production-secret
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=api.example.com
   DATABASE_URL=postgresql://...
   CORS_ALLOWED_ORIGINS=https://your-frontend.example.com
   CSRF_TRUSTED_ORIGINS=https://api.example.com,https://your-frontend.example.com
   ACCESS_TOKEN_LIFETIME_MINUTES=60
   REFRESH_TOKEN_LIFETIME_DAYS=7
   TIME_ZONE=Asia/Dubai
   GUNICORN_WORKERS=3
   GUNICORN_TIMEOUT=120
   ```

4. Deploy, then add a domain in Dokploy's **Domains** tab. Route it to container
   port `8000` and enable HTTPS. No manual Traefik labels are needed.
5. Use `/api/health/` for health monitoring and `/api/docs/` for Swagger.

The container runs Django deployment checks, applies committed migrations,
collects static files, and starts Gunicorn. Hosts, CORS origins, and CSRF origins
must be configured explicitly. Do not add trailing slashes to origin values.
The application trusts Dokploy's `X-Forwarded-Proto` header so HTTPS requests
are recognized correctly behind its proxy.

### Docker Compose service

Select Compose path `./docker-compose.yml`, add the same variables in Dokploy's
Environment editor, deploy, and attach the domain to service `web` on port
`8000`. Dokploy writes its environment editor values to `.env`; the Compose
file explicitly injects that file into the service.

Persistent uploaded files use the named `media` volume. The PostgreSQL database
is external and supplied through `DATABASE_URL`.

Purchase attachments are stored under `/app/media`. When using a Dockerfile
Application instead of Compose, add a Dokploy persistent volume mounted at
`/app/media`; otherwise uploaded attachments are lost when the container is
replaced.

Tests and validation:

```powershell
python manage.py check
python manage.py test
```

Before applying the normalized payment constraints in a populated environment:

1. Create and verify a PostgreSQL backup.
2. Run `python manage.py audit_payment_migration_data` (or `--format json`/`csv`).
3. Correct every blocking record through an approved, audited process; the command never modifies data.
4. Run the preflight again and require a zero exit code.
5. Apply migrations only after the audit is clean.

PostgreSQL CI uses a disposable `bakeryflow_test` service and the fail-closed
`config.settings_test_postgres` settings. See `docs/POSTGRESQL_TESTING.md`.

## Authentication and access

- `POST /api/auth/login/` with `email` and `password`
- `POST /api/auth/refresh/`, `POST /api/auth/logout/`
- `GET /api/auth/me/` returns role, assigned location, and `allowed_modules`
- `POST /api/auth/change-password/`

Administrators see all modules and locations. Other users must have the API's module in `allowed_modules`; users without `can_access_all_locations` are restricted to `assigned_location`. This is enforced server-side.

Demo accounts use `DEMO_PASSWORD` (development default `BakeryFlow2026!`): admin, purchase, production, warehouse, shop1, shop2, accounts, and manager at `@bakeryflow.local`.

Swagger: `/api/docs/`; ReDoc: `/api/redoc/`; schema: `/api/schema/`.

## Frontend integration

Set `VITE_API_BASE_URL=http://localhost:8000/api`. Send `Authorization: Bearer <access>` on API requests, refresh with the refresh token after a 401, and build navigation from `allowed_modules` returned by `/auth/me/`. API errors use `{success, message, errors}`. Transaction actions use endpoints such as `POST /purchases/{id}/post/` and `/cancel/`.

Stock transactions are read-only via the API and are created only by atomic domain services. Posted records are reversed rather than deleted.

## Current extension points

The schema includes production, transfers, sales returns, and payment allocations. Their more advanced posting/action services and additional analytical report endpoints can be expanded as the frontend switches from its local store to API calls. Celery and Redis configuration is ready but workers are not required for startup.
