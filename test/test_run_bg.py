import os
from pathlib import Path


def test_run_bg_last_line():
    path = Path("run_bg.sh")
    lines = path.read_text().splitlines()
    assert (
        lines[-1]
        == 'uv run watchfiles --filter python "uv run python -m telegram_auto_poster.main" telegram_auto_poster'
    )
    assert lines[-1] == lines[-1].strip()
    assert path.read_text().endswith("\n")


def test_run_bg_web_dashboard():
    path = Path("run_bg.sh")
    lines = path.read_text().splitlines()
    assert (
        'uv run watchfiles --filter python "uv run uvicorn telegram_auto_poster.web.app:app --host 0.0.0.0 --port ${WEB_PORT:-8000}" telegram_auto_poster/web &'
        in lines
    )


def test_run_bg_executable():
    assert os.access("run_bg.sh", os.X_OK)
