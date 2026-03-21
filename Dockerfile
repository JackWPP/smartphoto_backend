FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG PIP_INDEX_URL=http://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
ARG PIP_TRUSTED_HOST=mirrors.tuna.tsinghua.edu.cn

WORKDIR /app

COPY pyproject.toml Readme.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

RUN python -m pip install --upgrade pip \
    && pip config set global.index-url "${PIP_INDEX_URL}" \
    && pip config set global.trusted-host "${PIP_TRUSTED_HOST}" \
    && pip install .

EXPOSE 8000

CMD ["bash", "scripts/docker-api.sh"]
