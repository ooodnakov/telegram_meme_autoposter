import sys
import types

from pydantic import SecretStr

from telegram_auto_poster.utils.caption import generate_caption
from telegram_auto_poster.config import CONFIG


def _patch_ocr(monkeypatch, text: str | None, raise_err: bool = False) -> None:
    fake_pytesseract = types.SimpleNamespace()
    if raise_err:
        def _raise(*args, **kwargs):
            raise RuntimeError("ocr fail")
        fake_pytesseract.image_to_string = _raise
    else:
        fake_pytesseract.image_to_string = lambda img: text
    fake_image = types.SimpleNamespace(open=lambda path: None)
    fake_pil = types.ModuleType("PIL")
    fake_pil.Image = fake_image
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", fake_image)


def _patch_gemini(monkeypatch, response_text: str):
    holder: dict[str, object] = {}

    class FakeModel:
        def __init__(self, name):
            self.name = name
            self.prompt = None

        def generate_content(self, prompt):
            self.prompt = prompt
            return types.SimpleNamespace(text=response_text)

    def factory(name):
        m = FakeModel(name)
        holder["model"] = m
        return m

    fake_genai = types.SimpleNamespace(
        configure=lambda api_key: None,
        GenerativeModel=factory,
    )
    google_pkg = types.ModuleType("google")
    google_pkg.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    return holder


def test_generate_caption_ocr_failure(monkeypatch):
    _patch_ocr(monkeypatch, text=None, raise_err=True)
    orig = CONFIG.gemini.api_key
    CONFIG.gemini.api_key = SecretStr("k")
    try:
        assert generate_caption("dummy.jpg", "en") == ""
    finally:
        CONFIG.gemini.api_key = orig


def test_generate_caption_with_stub(monkeypatch):
    _patch_ocr(monkeypatch, text="Привет")
    _patch_gemini(monkeypatch, "Hello")
    orig = CONFIG.gemini.api_key
    CONFIG.gemini.api_key = SecretStr("k")
    try:
        result = generate_caption("dummy.jpg", "en")
        assert result == "Hello"
    finally:
        CONFIG.gemini.api_key = orig


def test_generate_caption_translation_prompt(monkeypatch):
    _patch_ocr(monkeypatch, text="hola")
    holder = _patch_gemini(monkeypatch, "hola")
    orig = CONFIG.gemini.api_key
    CONFIG.gemini.api_key = SecretStr("k")
    try:
        generate_caption("dummy.jpg", "fr")
        assert "fr" in holder["model"].prompt
    finally:
        CONFIG.gemini.api_key = orig
