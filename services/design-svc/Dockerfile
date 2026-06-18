# design-svc — thin probe-design orchestration layer. Built on svc-base.
#   docker build -f services/design-svc/Dockerfile -t refgen/design-svc:0.1.0 .
FROM refgen/svc-base:0.2.0

COPY services/design-svc/app/ ./app/

ENV SERVICE_NAME=design-svc \
    SERVICE_VERSION=0.1.0

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
