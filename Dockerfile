FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml Readme.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN pip install --upgrade pip \
    && pip install .

EXPOSE 8000

CMD ["bash", "scripts/docker-api.sh"]
