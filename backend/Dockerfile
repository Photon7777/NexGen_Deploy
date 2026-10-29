# Build from the repo root, because the API imports the shared nexlearn package:
#   docker build -f backend/Dockerfile -t nexlearn-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Exported from uv.lock with hashes (uv export --no-dev), so the image gets exactly the tested versions.
COPY backend/requirements.lock.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock.txt

COPY nexlearn ./nexlearn
COPY backend/app ./app

RUN useradd --create-home api
USER api

# Cloud Run sets PORT.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips="*"
