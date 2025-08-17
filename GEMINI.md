# Gemini Code Assistant Context

This document provides context for the Gemini Code Assistant to understand the project structure, technologies used, and development conventions.

## Project Overview

This project is a Telegram bot that automatically posts memes to a specified channel. It monitors a list of source channels for new media (images and videos), processes them by adding watermarks, and forwards them to a target channel after an administrator's approval. The bot also provides statistics on media processing and user engagement.

The project is written in Python and uses the following main technologies:

*   **Telegram Bot API**: The `python-telegram-bot` library is used to create and manage the Telegram bot.
*   **Telegram User API**: The `Telethon` library is used to monitor Telegram channels for new media.
*   **MinIO**: Used for object storage to store media files.
*   **Valkey**: Used for in-memory data storage to manage statistics.
*   **Docker**: The project includes a `Dockerfile` and `docker-compose.yaml` for containerization.

The application is divided into two main components:

1.  **The Bot (`bot.py`)**: Handles user interactions, such as commands and media submissions. It also manages the approval workflow for new media.
2.  **The Client (`client.py`)**: Monitors the source channels for new media and downloads them for processing.

## Building and Running

### Prerequisites

*   Python 3.12
*   MinIO server
*   Valkey server
*   A Telegram bot token and API credentials

### Installation

1.  Clone the repository.
2.  Create a `config.ini` file from the `config.example.ini` and fill in the required values.
3.  Install the dependencies:

    ```bash
    uv sync
    ```

### Running the Application

To run the application, use the following command:

```bash
uv run python -m telegram_auto_poster.main
```

Alternatively, you can use the provided `run_bg.sh` script to run the application in the background.

### Running with Docker

The project can also be run using Docker:

```bash
docker-compose up -d
```

## Development Conventions

### Code Style

The project uses the `ruff` linter and formatter to enforce a consistent code style. The configuration can be found in the `pyproject.toml` file.

### Testing

The project uses `pytest` for testing. The tests are located in the `test/` directory. To run the tests, use the following command:

```bash
uv run pytest -n auto
```

### Logging

The project uses the `loguru` library for logging. The logger is configured in the `telegram_auto_poster/utils/logger_setup.py` file.

### Configuration

The application is configured through a `config.ini` file and environment variables. The configuration is loaded by the `load_config()` function in the `telegram_auto_poster/config.py` file.
