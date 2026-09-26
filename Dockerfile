ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ARG BUILD_DATE=unknown
ARG VCS_REF=unknown
ARG VERSION=0.1.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

LABEL org.opencontainers.image.title="Manga News Private API" \
      org.opencontainers.image.description="Private self-hosted API for Manga News with cache and optional auth." \
      org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.version=$VERSION

RUN --mount=type=secret,id=custom_ca,target=/tmp/custom-ca.crt,required=false \
    if [ -s /tmp/custom-ca.crt ]; then \
        cp /tmp/custom-ca.crt /usr/local/share/ca-certificates/custom-ca.crt && \
        update-ca-certificates; \
    fi

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .env.example ./
COPY README.md ./

RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "20"]
