# Gemini Code Assistant Context

This document provides context for the Gemini Code Assistant to understand the project structure, technologies used, and development conventions.

## Project Overview

This project is a Telegram bot that automatically posts memes to a specified channel. It watches multiple source channels for new media (images and videos), adds a watermark, and forwards the content to a target channel after an administrator's approval. The system also sends feedback to submitters, maintains usage statistics, and includes a simple web dashboard for reviewing queued media.

The project is written in Python and uses the following technologies:

* **Telegram Bot API**: `python-telegram-bot` drives the interactive bot.
* **Telegram User API**: `Telethon` monitors channels for new media.
* **MinIO**: Stores original and processed media.
* **Valkey**: Keeps statistics in memory.
* **MySQL**: Stores the submission queue and user permissions for the web dashboard.
* **Docker**: Provides containerized deployment via `Dockerfile` and `docker-compose.yaml`.

The application is divided into three main components:

1. **Bot (`bot.py`)** – handles user commands, content submission, feedback, and admin approvals.
2. **Client (`client.py`)** – watches source channels and downloads media for processing.
3. **Web Dashboard (`web/`)** – FastAPI app for reviewing queued items and viewing analytics backed by MySQL.

## Building and Running

### Prerequisites

* Python 3.12 and [uv](https://github.com/astral-sh/uv)
* MinIO server
* Valkey server
* MySQL server
* A Telegram bot token and API credentials

### Installation

1. Clone the repository.
2. Create configuration files:
   ```bash
   cp config.example.ini config.ini
   cp .env.example .env
   ```
3. Install the dependencies:
   ```bash
   uv sync
   ```

### Running the Application

To run the bot, use:

```bash
uv run python -m telegram_auto_poster.main
```

You can also run both the bot and the dashboard in the background:

```bash
./run_bg.sh
```

### Running with Docker

The project can be run with Docker:

```bash
docker-compose up -d
```

## Development Conventions

### Code Style

Use `ruff` to keep imports sorted and code formatted:

```bash
uv run ruff check --select I --fix
uv run ruff check
uv run ruff format
```

Configuration for `ruff` resides in `pyproject.toml`.

### Testing

Tests live in the `test/` directory and are executed with:

```bash
uv run pytest -n auto
```

### Logging

Logging uses `loguru` with configuration in `telegram_auto_poster/utils/logger_setup.py`.

### Configuration

Settings are loaded from `config.ini` and environment variables by `load_config()` in `telegram_auto_poster/config.py`.

