#!/bin/bash
# Create required directories if they don't exist
mkdir -p photos videos

# Start the application
echo "Starting Telegram Meme Autoposter..."
python -m telegram_auto_poster.main 