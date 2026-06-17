# Runs the existing dx CLI (from refgen-platform/cli) in a container, pointed at
# the dxm gateway — so you get the real dx without installing anything on the host.
#   docker build -f docker/dx.Dockerfile -t dxm-dx:local ../refgen-platform/cli
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /cli
COPY . /cli
RUN pip install --no-cache-dir /cli \
        click rich questionary httpx prompt_toolkit websockets pyyaml

ENV DX_HOME=/root/.dx
ENTRYPOINT ["dx"]
