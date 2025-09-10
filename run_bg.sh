#!/bin/bash
set -e

trap "kill 0" EXIT

echo "Starting Telegram Meme Autoposter..."

# Wait for MinIO to be ready
echo "Waiting for MinIO to be ready..."
until $(curl --output /dev/null --silent --head --fail -H "Host: localhost" http://${MINIO_HOST:-minio}:${MINIO_PORT:-8999}/minio/health/live); do
  echo "Waiting for MinIO..."
  sleep 5
done
echo "MinIO is ready!"

# Create directories for temporary files
mkdir -p /workspace/tmp
mkdir -p /workspace/photos
mkdir -p /workspace/videos

# Start the web dashboard
echo "Starting web dashboard..."
uv run uvicorn telegram_auto_poster.web.app:app --host 0.0.0.0 --port ${WEB_PORT:-8000} &

# Pydoc is now served by the web dashboard
# echo "Starting pydoc server..."
# uv run python -m pydoc -p ${PYDOC_PORT:-8765} &

# Start the bot application
echo "Starting application..."
uv run python -m telegram_auto_poster.main
