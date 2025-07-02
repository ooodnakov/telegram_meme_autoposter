import os
from pathlib import Path


def test_run_bg_last_line():
    path = Path('run_bg.sh')
    lines = path.read_text().splitlines()
    assert lines[-1] == 'python -m telegram_auto_poster.main'
    assert lines[-1] == lines[-1].strip()
    assert path.read_text().endswith('\n')


def test_run_bg_executable():
    assert os.access('run_bg.sh', os.X_OK)

