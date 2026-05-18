FROM node:20-alpine AS adminfront-builder

WORKDIR /build/adminfront

COPY adminfront/package.json ./
RUN npm install

COPY adminfront/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml Readme.md alembic.ini ./
COPY app ./app
COPY alembic ./alembic
COPY scripts ./scripts
COPY --from=adminfront-builder /build/adminfront/dist ./adminfront/dist

RUN pip install --upgrade pip setuptools wheel \
    && pip install . \
    && chmod +x ./scripts/*.sh

EXPOSE 8000

ENV SERVICE_TYPE=api

ENTRYPOINT ["./scripts/docker-entrypoint.sh"]
