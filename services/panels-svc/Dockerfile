# panels-svc — built on the shared svc-base image.
#   docker build -f services/panels-svc/Dockerfile -t refgen/panels-svc:0.1.0 .
FROM refgen/svc-base:0.2.0

COPY services/panels-svc/app/ ./app/

ENV SERVICE_NAME=panels-svc \
    SERVICE_VERSION=0.1.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
