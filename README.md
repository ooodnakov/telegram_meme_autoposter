# Telegram Meme Autoposter

A Telegram bot + watcher that monitors source channels for media (photos/videos), watermarks and queues them for admin review, then posts to a target channel. Includes feedback to submitters, usage stats, and a simple web dashboard.

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
   Or run bot + dashboard together:
   ```bash
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
- Simple FastAPI dashboard for review/analytics
- MinIO-backed storage for originals/processed media

## Project Structure

- `telegram_auto_poster/main.py`: App entrypoint wiring bot + client
- `telegram_auto_poster/bot/`: Bot commands, handlers, permissions
- `telegram_auto_poster/client/`: Telethon client watching channels
- `telegram_auto_poster/web/`: FastAPI dashboard app
- `telegram_auto_poster/utils/`: Logging, storage, helpers
- `telegram_auto_poster/locales/`: I18n files and scripts
- `wiki/`: Project Wiki (git submodule)

## Web Dashboard & Docs

- Run standalone dashboard:
  ```bash
  uv run uvicorn telegram_auto_poster.web.app:app --host 0.0.0.0 --port 8000
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
