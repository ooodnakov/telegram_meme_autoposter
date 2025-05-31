# Telegram Meme Autoposter

A system that monitors various Telegram channels for media content (photos/videos), processes them, and forwards approved content to a target channel.

## Features

- Monitors multiple source channels for new media content
- Adds watermarks to images with configurable positioning
- Processes video content
- Allows admin approval or rejection of content
- Supports batching multiple approved items for posting at once
- Provides detailed statistics on media processing
- **NEW: Provides feedback to media submitters when their content is approved or rejected**
- **NEW: Enhanced admin permission system to control access to admin commands**
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

## Setup Instructions

1. Clone this repository
2. Configure environment variables or update the `config.py` file:
   - `TELEGRAM_BOT_TOKEN` - Telegram bot token
   - `ADMIN_USER_ID` - Telegram user ID for admin access
   - `TARGET_CHANNEL_ID` - Channel ID where approved media will be posted
   - `TELEGRAM_ADMIN_IDS` - Comma-separated list of admin Telegram user IDs
   - MinIO configuration (host, port, access keys)
3. Set up MinIO storage server (or use an existing one)
4. Install dependencies with `pip install -r requirements.txt`
5. Run the bot with `python -m telegram_auto_poster.main`

### Admin Configuration

You can configure admin users in multiple ways:

1. **Config file**: Add an `admin_ids` field in the `[Bot]` section of your `config.ini` file:
   ```ini
   [Bot]
   admin_ids = 12345678,87654321
   ```

2. **Environment variable**: Set the `TELEGRAM_ADMIN_IDS` environment variable:
   ```bash
   export TELEGRAM_ADMIN_IDS=12345678,87654321
   ```

3. **Default fallback**: If no admin IDs are specified, the bot will use the `bot_chat_id` as the admin ID.

## Architecture

The system consists of the following components:

1. **Telegram Bot**: Interface for users to submit content and for admins to moderate
2. **Media Processor**: Adds watermarks to images and processes video content
3. **Storage System**: MinIO-based storage for original and processed media
4. **Stats System**: Tracking system for monitoring performance and usage patterns
5. **Permissions System**: Controls access to admin commands

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 