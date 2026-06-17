# identity-svc — built on the shared svc-base image.
#   docker build -f services/identity-svc/Dockerfile -t refgen/identity-svc:0.1.0 .
# (build from the repo root so the base image is in scope)
FROM refgen/svc-base:0.2.0

COPY services/identity-svc/app/ ./app/

ENV SERVICE_NAME=identity-svc \
    SERVICE_VERSION=0.1.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
