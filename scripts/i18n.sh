#!/usr/bin/env bash
set -e
ROOT_DIR=$(dirname "$0")/..
LOCALE_DIR="$ROOT_DIR/telegram_auto_poster/locales"
uv run pybabel extract -o "$LOCALE_DIR/messages.pot" "$ROOT_DIR/telegram_auto_poster"
uv run pybabel update -i "$LOCALE_DIR/messages.pot" -d "$LOCALE_DIR"
uv run pybabel compile -d "$LOCALE_DIR"
