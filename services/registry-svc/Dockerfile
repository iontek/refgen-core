# registry-svc — MCP catalog + status (+ lifecycle later). Built on svc-base.
#   docker build -f services/registry-svc/Dockerfile -t refgen/registry-svc:0.1.0 .
FROM refgen/svc-base:0.2.0

COPY services/registry-svc/app/ ./app/

ENV SERVICE_NAME=registry-svc \
    SERVICE_VERSION=0.1.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
