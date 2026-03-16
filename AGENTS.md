# AGENTS Code Assistant Context

This file describes the current project architecture, tooling, and conventions for contributors and code assistants.

## Project Overview

Telegram Meme Autoposter is a Python-based moderation and publishing pipeline for Telegram media content.

It ingests media from:
- configured source channels (via Telethon), and
- direct user submissions to the bot (via python-telegram-bot).

Content is then processed (watermarking/deduplication/metadata), reviewed by admins, and either:
- scheduled or posted to destination channels,
- kept in batch flows, or
- moved to trash with restore/delete options.

A FastAPI backend serves a React SPA dashboard for moderation, analytics, and operational controls.

## Runtime Architecture

### 1) Entry point and orchestration
- `telegram_auto_poster/main.py`
  - Loads config
  - Starts bot polling and Telethon watcher concurrently
  - Handles graceful shutdown and stats flush

### 2) Bot runtime
- `telegram_auto_poster/bot/`
  - `bot.py`: bot initialization and lifecycle
  - `commands.py`, `callbacks.py`, `handlers.py`: command and moderation flows
  - `permissions.py`: role and access controls

### 3) Channel watcher
- `telegram_auto_poster/client/client.py`
  - Subscribes to source channels
  - Fetches incoming media/messages for processing pipeline

### 4) Media processing
- `telegram_auto_poster/media/photo.py`
- `telegram_auto_poster/media/video.py`
  - Watermark and transform photo/video assets

### 5) Web API + dashboard shell
- `telegram_auto_poster/web/app.py`
  - Authentication/session handling
  - API endpoints for suggestions, queue, batch, posts, trash, events, stats, leaderboard, and settings
  - Serves frontend build from `frontend/dist`

### 6) Shared services/utilities
- `telegram_auto_poster/utils/`
  - Storage layer (MinIO), stats/leaderboard (Valkey), scheduling/jobs, channel analytics, i18n, trash lifecycle, helpers

### 7) Frontend SPA
- `frontend/`
  - Vite + React + TypeScript admin dashboard
  - Route-based moderation/operations UI

## Storage and State

- **MinIO**: object storage for originals, processed media, and metadata sidecars.
- **Valkey**: in-memory counters, analytics, and leaderboard/event-related state.

## Build and Run

### Prerequisites
- Python 3.12
- `uv`
- Node.js + npm (for frontend)
- MinIO and Valkey instances
- Telegram Bot token + Telegram API credentials

### Install
```bash
cp config.example.ini config.ini
cp .env.example .env
uv sync
cd frontend && npm install && cd ..
```

### Run backend (bot + watcher)
```bash
uv run python -m telegram_auto_poster.main
```

### Run dashboard API server directly
```bash
uv run uvicorn telegram_auto_poster.web.app:app --host 0.0.0.0 --port 8000
```

### Build frontend for FastAPI serving
```bash
cd frontend && npm run build && cd ..
```

### Docker
```bash
docker-compose up -d --build
```

## Development Conventions

### Formatting and linting
Use Ruff:
```bash
uv run ruff check --select I --fix
uv run ruff check
uv run ruff format
```

### Testing
Backend tests:
```bash
uv run pytest -n auto
```

Frontend tests (inside `frontend/`):
```bash
npm test
```

### Logging
- `loguru` configuration is in `telegram_auto_poster/utils/logger_setup.py`.

### Configuration
- Loaded from `config.ini` + environment variables via `load_config()` in `telegram_auto_poster/config.py`.
