#!/bin/bash
set -e

echo "Starting Telegram Meme Autoposter..."

# Wait for MinIO to be ready
echo "Waiting for MinIO to be ready..."
until $(curl --output /dev/null --silent --head --fail http://${MINIO_HOST:-minio}:${MINIO_PORT:-9000}/minio/health/live); do
  echo "Waiting for MinIO..."
  sleep 5
done
echo "MinIO is ready!"

# Create directories for temporary files
mkdir -p /app/tmp
mkdir -p /app/photos
mkdir -p /app/videos

cd /app

# Start the application
echo "Starting application..."
python -m telegram_auto_poster.main
