# edge-gateway — built on the shared svc-base image (httpx comes from svc_base).
#   docker build -f services/gateway/Dockerfile -t refgen/gateway:0.1.0 .
FROM refgen/svc-base:0.2.0

COPY services/gateway/app/ ./app/

ENV SERVICE_NAME=edge-gateway \
    SERVICE_VERSION=0.1.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
