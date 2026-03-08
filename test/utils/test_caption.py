import sys
import types

from pydantic import SecretStr

from telegram_auto_poster.config import CONFIG
from telegram_auto_poster.utils.caption import (
    extract_ocr_text,
    generate_caption,
    get_tesseract_info,
)


def _patch_ocr(monkeypatch, text: str | None, raise_err: bool = False) -> None:
    fake_pytesseract = types.SimpleNamespace()
    if raise_err:

        def _raise(*args, **kwargs):
            raise RuntimeError("ocr fail")

        fake_pytesseract.image_to_string = _raise
    else:
        fake_pytesseract.image_to_string = lambda img, lang=None: text
    fake_pytesseract.get_tesseract_version = lambda: "5.3.0"

    class FakeImageHandle:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_image = types.SimpleNamespace(open=lambda path: FakeImageHandle())
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
        model = FakeModel(name)
        holder["model"] = model
        return model

    fake_genai = types.SimpleNamespace(GenerativeModel=factory)
    import telegram_auto_poster.utils.caption as caption_module

    monkeypatch.setattr(caption_module, "genai", fake_genai)
    return holder


def test_extract_ocr_text_failure(monkeypatch):
    _patch_ocr(monkeypatch, text=None, raise_err=True)
    result = extract_ocr_text("dummy.jpg", "eng")
    assert result.status == "failed"
    assert result.text == ""


def test_get_tesseract_info_with_stub(monkeypatch):
    _patch_ocr(monkeypatch, text="hola")
    info = get_tesseract_info()
    assert info.available is True
    assert info.version == "5.3.0"


def test_generate_caption_with_stub(monkeypatch):
    _patch_ocr(monkeypatch, text="Привет")
    _patch_gemini(monkeypatch, "Hello")
    monkeypatch.setattr(CONFIG.gemini, "api_key", SecretStr("k"))
    result = generate_caption("dummy.jpg", "en", "eng+rus")
    assert result == "Hello"


def test_generate_caption_translation_prompt(monkeypatch):
    _patch_ocr(monkeypatch, text="hola")
    holder = _patch_gemini(monkeypatch, "hola")
    monkeypatch.setattr(CONFIG.gemini, "api_key", SecretStr("k"))
    generate_caption("dummy.jpg", "fr")
    assert "fr" in holder["model"].prompt
