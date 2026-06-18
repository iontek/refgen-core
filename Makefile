# refgen-core — barebone microservices. Everything runs in Docker; host stays clean.
.PHONY: help base build up down logs ps test

help:
	@echo "make base   - build the shared svc-base image"
	@echo "make build  - build all service images"
	@echo "make up     - start the stack (docker compose up -d)"
	@echo "make down   - stop the stack"
	@echo "make logs   - tail logs"
	@echo "make ps     - container status"
	@echo "make test   - run tests in an ephemeral container (host stays clean)"
	@echo "make dxm ARGS=\"...\" - run the dxm client (Docker) against the gateway, e.g. ARGS=\"panel list\""
	@echo "make migrate-panels  - one-time ETL: old platform SQLite panels -> panels-svc Postgres"
	@echo "make migrate-users   - one-time ETL: old platform auth_users -> identity-svc Postgres"

base:
	docker build -f docker/svc-base.Dockerfile -t refgen/svc-base:0.2.0 .

build: base
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

# Tests run inside a throwaway container against a READ-ONLY mount of the repo,
# so nothing (venv, caches, build artifacts) is ever written to the host.
test:
	docker run --rm -v "$(CURDIR)":/work:ro -e PYTHONDONTWRITEBYTECODE=1 \
		python:3.13-slim sh -c "cp -r /work/libs/svc_base /tmp/pkg && pip install -q /tmp/pkg pytest==8.3.4 httpx==0.28.1 && python -m pytest /tmp/pkg/tests -q"

# The dxm client = the dx CLI in a container, pointed at the dxm gateway. Uses
# its OWN config volume, so it never touches the host's ~/.dx (the old `dx` that
# talks to the platform on :8001). Two separate commands, two separate configs.
#   make dxm ARGS="login -u admin -p admin"
#   make dxm ARGS="panel list"
#   make dxm                      # bare -> interactive TUI
DX_SRC ?= ../refgen-platform/cli
.PHONY: dxm
dxm:
	@docker image inspect dxm-dx:local >/dev/null 2>&1 || \
		docker build -q -f docker/dx.Dockerfile -t dxm-dx:local "$(DX_SRC)" >/dev/null
	@docker run --rm -it \
		-v dxm-dxconfig:/root/.dx \
		-e DX_SERVER=http://host.docker.internal:8090 \
		--add-host=host.docker.internal:host-gateway \
		dxm-dx:local $(ARGS)

# One-time ETL: migrate panels from the old platform SQLite into panels-svc Postgres.
# Reads the old DB read-only via the platform's `refgen-core` container volumes
# (copied to /tmp inside the job), writes to the dxm panels DB. Lossless:
# preserves content_hash + legacy ids. Requires the old platform to be running.
.PHONY: migrate-panels
migrate-panels:
	docker run --rm --volumes-from refgen-core:ro \
		-v "$(CURDIR)/migrations":/migrations:ro \
		--network "$$(docker inspect dxm-postgres-1 -f '{{range $$k,$$v := .NetworkSettings.Networks}}{{$$k}}{{end}}')" \
		--user root \
		-e DATABASE_URL=postgresql://postgres:postgres@postgres:5432/panels \
		refgen/svc-base:0.2.0 \
		sh -c 'cp /workspace/db/refgen.db* /tmp/ 2>/dev/null; OLD_DB=/tmp/refgen.db python /migrations/migrate_panels.py'

.PHONY: migrate-users
migrate-users:
	docker run --rm --volumes-from refgen-core:ro \
		-v "$(CURDIR)/migrations":/migrations:ro \
		--network "$$(docker inspect dxm-postgres-1 -f '{{range $$k,$$v := .NetworkSettings.Networks}}{{$$k}}{{end}}')" \
		--user root \
		-e DATABASE_URL=postgresql://postgres:postgres@postgres:5432/identity \
		refgen/svc-base:0.2.0 \
		sh -c 'cp /workspace/db/refgen.db* /tmp/ 2>/dev/null; OLD_DB=/tmp/refgen.db python /migrations/migrate_users.py'
