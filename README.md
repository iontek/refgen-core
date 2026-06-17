# refgen-core

Barebone microservices for the RefGen control plane. Each service is a small,
self-contained FastAPI app that owns its own data and talks to the others over
HTTP — mirroring the platform's existing MCP-substrate conventions (shared base
image, `/healthz` + `/version`, name-based discovery on a Docker network).

## Layout

```
refgen-core/
├── libs/svc_base/        # the shared "barebone framework" every service inherits
├── services/
│   └── _template/        # the per-service skeleton (copy to start a new service)
├── docker/
│   └── svc-base.Dockerfile   # shared base image: refgen/svc-base
├── docker-compose.yml    # the local "city" of services
└── Makefile
```

## What svc_base gives every service

- `create_app(settings)` — a wired FastAPI app
- `/healthz` and `/version` (the Docker healthcheck hits `/healthz`)
- structured logging with a request-id that follows a call across services
- JWT verification (`Depends(require_auth)`) using a shared signing key
- a uniform JSON error shape

A service only writes what's unique to it: its routes (`app/api/`), its logic
(`app/domain/`), its data (`app/models/`, `app/db.py`).

## Run it locally (no Docker)

```bash
make venv     # one-time: create .venv, install svc_base + template (editable)
make test     # run the template's tests
. .venv/bin/activate && cd services/_template && uvicorn app.main:app --reload
# then: curl localhost:8000/healthz   curl localhost:8000/api/ping
```

## Run it in Docker

```bash
make base     # build refgen/svc-base
make build    # build service images
make up       # start the stack
curl localhost:8010/healthz
```

## Roadmap

Services are extracted from the existing `refgen-platform` Django core, one at a
time (strangler-fig), each stamped from `services/_template`:

1. **edge-gateway** — single front door; routing + JWT check + the shell
2. **identity-svc** — users, login/tokens, permissions  *(first extraction)*
3. **design-svc** — probe/bait pipeline + background jobs  *(highest payoff)*
4. **panels-svc** — panels, genes, versions, the state machine  *(the domain heart)*

The MCP substrate (18 servers) stays as-is — it's already microservices.
