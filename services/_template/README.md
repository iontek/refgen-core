# Service template

The skeleton every refgen-core service is stamped from. To create a new
service (e.g. `identity-svc`):

1. Copy this directory: `cp -r services/_template services/identity-svc`
2. Rename the package details in `app/config.py` (`service_name`, `service_version`).
3. Replace the example `app/api/routes.py`, `app/domain/`, and `app/models/`
   with the real thing. Define the service's tables in `app/db.py`.
4. Add it to `docker-compose.yml`.

## Layout

| Path | Role |
|------|------|
| `app/main.py` | Entry point — builds the app from `svc_base`, mounts routes |
| `app/config.py` | Settings (env-driven), incl. this service's `database_url` |
| `app/api/` | Front counter — HTTP endpoints (thin) |
| `app/domain/` | Back room — the real logic (no HTTP, easy to test) |
| `app/models/` | Data shapes (Pydantic) and, later, DB tables |
| `app/db.py` | Connection to this service's own database |
| `tests/` | Tests |

Everything shared (health, version, logging, request-ids, JWT auth, error
shape) lives in `svc_base` and is inherited — not repeated here.
