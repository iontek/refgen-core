# Shared base image for all refgen-core services.
# Mirrors the platform's MCP base pattern (tini PID 1, non-root, curl healthcheck).
# Build from the repo root so libs/ is in the build context:
#   docker build -f docker/svc-base.Dockerfile -t refgen/svc-base:0.1.0 .
#
# Concrete services:  FROM refgen/svc-base:0.1.0
#                     COPY services/<name>/app/ ./app/
# and they inherit the framework + /healthz + /version + JWT auth.

FROM python:3.13-slim

# tini = PID 1: forwards SIGTERM, reaps zombies -> docker stop is instant
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# non-root
RUN useradd -u 1000 -m svc

WORKDIR /app

# install the shared framework (pulls fastapi/uvicorn/pydantic/pyjwt)
COPY libs/svc_base/ /opt/svc/svc_base_pkg/
RUN pip install --no-cache-dir /opt/svc/svc_base_pkg/

ENV PYTHONPATH=/app \
    SERVICE_PORT=8000

USER svc
EXPOSE 8000
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["tini", "--"]
