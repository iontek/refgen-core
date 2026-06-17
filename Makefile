# refgen-core — barebone microservices.
.PHONY: help base build up down logs ps test fmt venv

help:
	@echo "make base   - build the shared svc-base image"
	@echo "make build  - build all service images"
	@echo "make up      - start the stack (docker compose up -d)"
	@echo "make down    - stop the stack"
	@echo "make logs    - tail logs"
	@echo "make ps      - container status"
	@echo "make venv    - local dev venv (installs svc_base + template, editable)"
	@echo "make test    - run the test suite locally (needs 'make venv' first)"

base:
	docker build -f docker/svc-base.Dockerfile -t refgen/svc-base:0.1.0 .

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

venv:
	python3 -m venv .venv
	. .venv/bin/activate && pip install -q --upgrade pip \
		&& pip install -q -e libs/svc_base \
		&& pip install -q -e "services/_template[dev]"

test:
	. .venv/bin/activate && cd services/_template && python -m pytest -q
