# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin/:$PATH"
WORKDIR /workspace

# Install build tools and uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh

COPY pyproject.toml uv.lock ./
RUN uv sync

FROM python:3.12-slim AS runtime
ENV DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin/:$PATH"
WORKDIR /workspace

# Runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends netcat-traditional gcc \
    wget \
    ffmpeg \
    htop \
    git \
    curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh


COPY --from=builder /root/.local /root/.local
COPY --from=builder /workspace/.venv /workspace/.venv  

COPY ./telegram_auto_poster ./telegram_auto_poster
COPY run_bg.sh /run_bg.sh
RUN chmod +x /run_bg.sh

COPY healthcheck.py /healthcheck.py
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD ["python", "/healthcheck.py"]

ENTRYPOINT ["/run_bg.sh"]
