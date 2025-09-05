# Telegram Meme Autoposter

A system that monitors various Telegram channels for media content (photos/videos), processes them, and forwards approved content to a target channel.

## Features

- Monitors multiple source channels for new media content
- Adds watermarks to images with configurable positioning
- Processes video content
- Allows admin approval or rejection of content
- Supports batching multiple approved items for posting at once
- Provides detailed statistics on media processing
- Automatically sends a daily statistics report at midnight
- Stores statistics in a Valkey server for fast access
- **NEW: Provides feedback to media submitters when their content is approved or rejected**
- **NEW: Enhanced admin permission system to control access to admin commands**
- **NEW: Simple web dashboard for reviewing queued media and viewing analytics**
- Stores media in MinIO object storage for efficient processing

## User Features

Users can now interact with the bot in the following ways:

1. **Submit Content**: Users can send photos and videos directly to the bot
2. **Receive Feedback**: Users will get notifications when their content is:
   - Approved and scheduled for posting
   - Approved and immediately posted
   - Rejected by the admin

## Admin Features

- `/start` - Initialize the bot
- `/help` - Display available commands
- `/sendall` - Send all approved media in the batch to the target channel
- `/stats` - View bot statistics including processing counts and performance metrics
- `/reset_stats` - Reset daily statistics
- `/save_stats` - Force save statistics to disk

All admin commands are protected with permission checks to ensure only authorized users can access them.

## Architecture

The system consists of the following components:

1. **Telegram Bot**: Interface for users to submit content and for admins to moderate
2. **Media Processor**: Adds watermarks to images and processes video content
3. **Storage System**: MinIO-based storage for original and processed media
4. **Stats System**: Tracking system for monitoring performance and usage patterns
5. **Permissions System**: Controls access to admin commands

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python 3.12
- [uv](https://github.com/astral-sh/uv)
- Docker
- Docker Compose

### Installation

1.  **Clone the repository**
    ```bash
    git clone https://github.com/your_username/telegram-meme-autoposter.git
    cd telegram-meme-autoposter
    ```

2.  **Create a virtual environment and install dependencies**
    ```bash
    uv sync
    ```

3.  **Set up environment variables**

    Create a `.env` file by copying the `env.example` file and fill in the required values.

    ```bash
    cp env.example .env
    ```

4.  **Run the application**
    ```bash
    uv run python -m telegram_auto_poster.main
    ```

    Or start both the bot and dashboard together:

    ```bash
    ./run_bg.sh
    ```

5.  **Launch the web dashboard** (if not using `run_bg.sh` or Docker Compose)
    ```bash
    uv run uvicorn telegram_auto_poster.web.app:app --host 0.0.0.0 --port 8000
    ```

### Translations

Localization files live in `telegram_auto_poster/locales`.  To extract new
messages and compile `.mo` files after updating translations run:

```bash
./scripts/i18n.sh
```

The default language and per-user overrides can be configured in `config.ini`
under the `[I18n]` section.

## Running with Docker

You can also run the application using Docker and Docker Compose.

1.  **Set up environment variables**

    Create a `.env` file by copying the `env.example` file and fill in the required values.

    ```bash
    cp env.example .env
    ```

2.  **Build and run the Docker container**
    ```bash
    docker-compose up --build
    ```

The application will be running in a container, and you can view the logs using `docker-compose logs -f`. The web dashboard will be available at `http://localhost:8000`.

## Contributing

We welcome contributions to this project. Please follow these steps to contribute:

1.  **Fork the repository**
2.  **Create a new branch**
    ```bash
    git checkout -b feature/your-feature-name
    ```
3.  **Make your changes**
4.  **Commit your changes**
    ```bash
    git commit -m "feat: add your feature"
    ```
5.  **Push to the branch**
    ```bash
    git push origin feature/your-feature-name
    ```
6.  **Create a pull request**

Please make sure your code follows the project's coding style and that you have added tests for any new functionality.