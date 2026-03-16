# Telegram Meme Autoposter

A Telegram automation platform that ingests media from source channels and direct bot submissions, processes it (watermarking, deduplication, metadata), and routes it through moderation flows before publishing to destination channels. The app includes a Python backend, a React SPA admin dashboard, and background scheduling/analytics utilities.

## Current Architecture

The application is split into clear runtime layers:

1. **Ingestion layer**
   - `telegram_auto_poster/client/client.py` uses Telethon to monitor source channels and download candidate media.
   - `telegram_auto_poster/bot/handlers.py` accepts user submissions through `python-telegram-bot`.
2. **Processing layer**
   - `telegram_auto_poster/media/photo.py` and `telegram_auto_poster/media/video.py` apply watermarks and transformations.
   - `telegram_auto_poster/utils/deduplication.py`, `caption.py`, and related helpers normalize posts before review.
3. **Moderation & publishing layer**
   - `telegram_auto_poster/web/app.py` exposes API endpoints consumed by the SPA for queue review, scheduling, trash/restore, events, settings, and stats.
   - Moderation actions move objects between storage prefixes (`processed`, `scheduled`, `posted`, `trash`) and can trigger immediate posting or scheduled publishing.
4. **Storage and state layer**
   - MinIO stores media binaries and metadata sidecars.
   - Valkey-backed utilities in `telegram_auto_poster/utils/stats.py` and related modules store counters, leaderboard data, and event snapshots.
5. **Frontend layer**
   - `frontend/` is a Vite + React + TypeScript SPA with route-based pages for suggestions, queue, batch, posts, trash, stats, leaderboard, jobs, and settings.
   - Built assets are served by FastAPI from `frontend/dist`.

## Quick Setup

Follow these steps to get running fast. For expanded docs, see the Wiki.

1. Clone and init submodules
   ```bash
   git clone https://github.com/ooodnakov/telegram_meme_autoposter.git
   cd telegram_meme_autoposter
   git submodule update --init --recursive
   ```
2. Install dependencies (Python 3.12 + uv)
   ```bash
   uv sync
   ```
   And install the dashboard dependencies:
   ```bash
   cd frontend
   npm install
   cd ..
   ```
3. Create config and env files
   ```bash
   cp config.example.ini config.ini
   cp .env.example .env
   ```
4. Fill in credentials and endpoints
   - Telegram Bot token and API ID/Hash
   - MinIO endpoint, access/secret keys, bucket
   - Valkey host/port
   - Target channel and admin IDs in `config.ini`
5. Run the app
   ```bash
   uv run python -m telegram_auto_poster.main
   ```
   Build the dashboard bundle and run bot + dashboard together:
   ```bash
   cd frontend && npm run build && cd ..
   ./run_bg.sh
   ```

## Configuration highlights

`config.ini` controls most behaviour. In addition to credentials, you can now:

- Configure attribution strings and the default suggestion caption under `[Branding]`.
- Change watermark assets, relative size, and transparency for images via `[WatermarkImage]`.
- Tune video watermark path, size range, and animation speed in `[WatermarkVideo]`.

Every option can also be overridden with environment variables (e.g. `BRANDING_ATTRIBUTION`,
`WATERMARK_IMAGE_PATH`).

## Documentation & Wiki

- Wiki (GitHub): https://github.com/ooodnakov/telegram_meme_autoposter/wiki
- Local copy (submodule): `wiki/Home.md`

Key topics to start with:
- Setup and configuration (env + `config.ini`)
- Running locally vs Docker
- Admin workflow and permissions

## Features

- Watches multiple source channels (Telethon)
- Watermarks images and processes videos
- Admin approval queue with batch posting
- Feedback to submitters on approval/rejection
- Configurable trash bin for rejected posts with restore support
- Daily stats and Valkey-backed metrics
- React dashboard served by FastAPI for review/analytics
- MinIO-backed storage for originals/processed media

## Project Structure

- `telegram_auto_poster/main.py`: Async entrypoint orchestrating bot polling + channel watcher lifecycle.
- `telegram_auto_poster/bot/`: Bot runtime (`bot.py`) and command/callback/handler modules.
- `telegram_auto_poster/client/`: Telethon ingestion client for monitored channels.
- `telegram_auto_poster/media/`: Image/video processing pipelines.
- `telegram_auto_poster/web/`: FastAPI app providing auth, API endpoints, and static SPA serving.
- `telegram_auto_poster/utils/`: Shared services (storage, stats, scheduler, jobs, i18n, trash, analytics).
- `frontend/`: React admin dashboard source code and tests.
- `test/`: Python test suite for backend behavior.
- `wiki/`: Project Wiki content (submodule).

## Web Dashboard & Docs

- Build the dashboard and run the backend shell:
  ```bash
  cd frontend && npm run build && cd ..
  uv run uvicorn telegram_auto_poster.web.app:app --host 0.0.0.0 --port 8000
  ```
- Frontend development server:
  ```bash
  cd frontend
  npm run dev
  ```
- Built-in pydoc browser after start: `http://localhost:8000/pydoc/`
  - Example: `http://localhost:8000/pydoc/telegram_auto_poster.utils.storage`

## Translations

Localization files live in `telegram_auto_poster/locales`. To extract and compile after updating translations:

```bash
./scripts/i18n.sh
```

Default language and per-user overrides are configured in `config.ini` under `[I18n]`.

## Running with Docker

1. Prepare env and config
   ```bash
   cp config.example.ini config.ini
   cp .env.example .env
   ```
2. Start services
   ```bash
   docker-compose up -d --build
   ```

Dashboard: `http://localhost:8000`. Logs: `docker-compose logs -f`.

See the Wiki for full Docker notes and production tips.

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Commit changes
   ```bash
   git commit -m "feat: add your feature"
   ```
4. Push and open a PR
   ```bash
   git push origin feature/your-feature-name
   ```

Before submitting, ensure style checks pass and tests are added when applicable.
