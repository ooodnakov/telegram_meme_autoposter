# Telegram Meme Autoposter

An automated system that monitors specified Telegram channels for new media content (images and videos), processes them, and forwards selected content to a target channel.

## Features

- **Media Monitoring**: Automatically monitors selected Telegram channels for new photo and video posts
- **Content Review**: Posts media to a review bot where users can approve/reject content
- **Media Processing**: Supports both images and videos
- **Batch Operations**: Commands for sending and deleting batches of media
- **Docker Support**: Fully containerized application with Docker and Docker Compose
- **MinIO Integration**: Uses MinIO for storage of media files

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- Telegram API credentials (API ID and Hash)
- Telegram Bot Token

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/telegram_meme_autoposter.git
   cd telegram_meme_autoposter
   ```

2. **Configure the application**
   - Copy the example configuration file:
     ```bash
     cp config.ini.example config.ini
     ```
   - Edit `config.ini` with your Telegram credentials:
     ```ini
     [Telegram]
     api_id = YOUR_API_ID
     api_hash = YOUR_API_HASH
     username = YOUR_USERNAME
     target_channel = @your_target_channel
     [Bot]
     bot_token = YOUR_BOT_TOKEN
     bot_username = @your_bot_username
     bot_chat_id = YOUR_BOT_CHAT_ID
     ```

3. **Docker Setup**
   - Make sure Docker and Docker Compose are installed
   - Run the service:
     ```bash
     docker-compose up -d
     ```

## Usage

### Bot Commands

- `/start` - Start the bot
- `/get` - Get the current chat ID
- `/ok` - Approve a media item
- `/notok` - Reject a media item
- `/send_batch` - Send a batch of approved media to the target channel
- `/delete_batch` - Delete a batch of media
- `/luba` - Send a special meme

### File Structure

- `telegram_auto_poster/` - Main package directory
  - `bot/` - Telegram bot implementation
  - `client/` - Telethon client for monitoring channels
  - `media/` - Media processing logic
  - `utils/` - Utility functions
- `photos/` and `videos/` - Directories for storing downloaded media
- `tmp/` - Directory for temporary files

## Development

### Installing dependencies

```bash
pip install -r requirements.txt
```

### Running locally

```bash
python -m telegram_auto_poster
```


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 