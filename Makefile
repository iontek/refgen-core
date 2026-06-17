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
