import asyncio
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from telegram_auto_poster.utils.captioner import generate_captions, DEFAULT_CAPTIONS


@pytest.mark.asyncio
async def test_generate_captions_fallback(tmp_path, monkeypatch):
    img = tmp_path / "i.jpg"
    img.write_bytes(b"123")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captions = await generate_captions(str(img))
    assert captions == DEFAULT_CAPTIONS


@pytest.mark.asyncio
async def test_generate_captions_openai(tmp_path, monkeypatch):
    img = tmp_path / "i.jpg"
    img.write_bytes(b"123")

    monkeypatch.setenv("OPENAI_API_KEY", "key")

    class FakeResponse:
        def __init__(self):
            self.choices = [
                SimpleNamespace(message=SimpleNamespace(content="- a\n- b"))
            ]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    return FakeResponse()

    fake_openai = ModuleType("openai")
    fake_openai.AsyncOpenAI = lambda api_key: FakeClient()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    captions = await generate_captions(str(img), n=2)
    assert captions == ["a", "b"]
