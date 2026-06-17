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
	@echo "make dx ARGS=\"...\" - run the dx CLI (Docker) against the gateway, e.g. ARGS=\"panel list\""

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

# Real dx CLI in a container, pointed at the gateway. Login persists in a named
# volume so it survives between calls. Host stays clean (nothing installed).
#   make dx ARGS="login -u admin -p admin"
#   make dx ARGS="panel list"
#   make dx                       # bare -> interactive TUI
DX_SRC ?= ../refgen-platform/cli
.PHONY: dx
dx:
	@docker image inspect dxm-dx:local >/dev/null 2>&1 || \
		docker build -q -f docker/dx.Dockerfile -t dxm-dx:local "$(DX_SRC)" >/dev/null
	@docker run --rm -it \
		-v dxm-dxconfig:/root/.dx \
		-e DX_SERVER=http://host.docker.internal:8090 \
		--add-host=host.docker.internal:host-gateway \
		dxm-dx:local $(ARGS)
