# syntax=docker/dockerfile:1

FROM python:3.12-slim AS python-builder
ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin/:$PATH"
WORKDIR /workspace

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

COPY pyproject.toml uv.lock ./
RUN uv sync

FROM node:22-slim AS frontend-builder
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin/:$PATH"
WORKDIR /workspace

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    netcat-traditional \
    gcc \
    wget \
    ffmpeg \
    htop \
    git \
    tesseract-ocr \
    libtesseract-dev \
    curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

COPY --from=python-builder /root/.local /root/.local
COPY --from=python-builder /workspace/.venv /workspace/.venv

COPY pyproject.toml uv.lock ./
COPY telegram_auto_poster ./telegram_auto_poster
COPY frontend/package.json ./frontend/package.json
COPY --from=frontend-builder /frontend/dist ./frontend/dist
COPY run_bg.sh /run_bg.sh
RUN chmod +x /run_bg.sh

ENTRYPOINT ["/run_bg.sh"]
