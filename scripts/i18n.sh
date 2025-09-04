#!/usr/bin/env bash
set -e
ROOT_DIR=$(dirname "$0")/..
LOCALE_DIR="$ROOT_DIR/telegram_auto_poster/locales"
pybabel extract -o "$LOCALE_DIR/messages.pot" "$ROOT_DIR/telegram_auto_poster"
pybabel update -i "$LOCALE_DIR/messages.pot" -d "$LOCALE_DIR"
pybabel compile -d "$LOCALE_DIR"
