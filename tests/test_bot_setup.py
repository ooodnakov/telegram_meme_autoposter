import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock


class DummyApp:
    def __init__(self):
        self.bot = SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(first_name="t", username="t")))
        self.bot_data = {}
        self.handlers = []
        self.updater = SimpleNamespace()

    def add_handler(self, handler, *a, **k):
        self.handlers.append(handler)

    async def initialize(self):
        pass


class DummyBuilder:
    def token(self, _):
        return self

    def build(self):
        return DummyApp()


def test_setup(monkeypatch, setup_bot_modules):
    modules = setup_bot_modules()
    bot_module = modules.bot

    monkeypatch.setattr(bot_module, "ApplicationBuilder", DummyBuilder)

    tb = bot_module.TelegramMemeBot()
    app = asyncio.run(tb.setup())

    assert app.bot_data["chat_id"] == "1"
    assert app.bot_data["target_channel_id"] == "@c"
    assert app.bot_data["admin_ids"] == [1]
