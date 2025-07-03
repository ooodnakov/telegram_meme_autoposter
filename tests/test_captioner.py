import asyncio
import os
from pathlib import Path

import pytest

from telegram_auto_poster.utils.captioner import generate_captions, DEFAULT_CAPTIONS


@pytest.mark.asyncio
async def test_generate_captions_fallback(tmp_path, monkeypatch):
    img = tmp_path / "i.jpg"
    img.write_bytes(b"123")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captions = await generate_captions(str(img))
    assert captions == DEFAULT_CAPTIONS
