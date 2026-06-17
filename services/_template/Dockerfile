# A concrete service: inherit the shared base, add this service's code.
#   docker build -f services/_template/Dockerfile -t refgen/template-svc:0.1.0 .
# (build from the repo root so the base image is in scope)
FROM refgen/svc-base:0.1.0

COPY services/_template/app/ ./app/

ENV SERVICE_NAME=template-svc \
    SERVICE_VERSION=0.1.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
