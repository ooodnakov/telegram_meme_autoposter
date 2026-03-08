"""OCR extraction and caption generation helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass

from loguru import logger
from telegram_auto_poster.config import CONFIG

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional dependency
    genai = None


@dataclass(slots=True)
class OCRResult:
    """Structured OCR result for media processing and backfill jobs."""

    text: str
    status: str
    error: str | None = None
    duration_seconds: float = 0.0

    @property
    def has_text(self) -> bool:
        """Return whether OCR extracted any non-empty text."""

        return bool(self.text)


@dataclass(slots=True)
class TesseractInfo:
    """Runtime information about the OCR engine."""

    available: bool
    version: str | None = None
    error: str | None = None


def configure_gemini() -> None:
    """Configure the Gemini client once at application startup."""
    if not genai or not CONFIG.gemini.api_key:
        return
    api_key = CONFIG.gemini.api_key.get_secret_value()
    if api_key:
        genai.configure(api_key=api_key)


def get_tesseract_info() -> TesseractInfo:
    """Return the availability and version of the local Tesseract engine."""

    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover - import failure
        return TesseractInfo(available=False, error=str(exc))

    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception as exc:
        return TesseractInfo(available=False, error=str(exc))
    return TesseractInfo(available=True, version=version)


def extract_ocr_text(media_path: str, languages: str | None = None) -> OCRResult:
    """Extract text from an image using Tesseract OCR."""

    start_time = time.perf_counter()

    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - import failure
        logger.error(f"OCR dependencies missing: {exc}")
        return OCRResult(
            text="",
            status="failed",
            error=str(exc),
            duration_seconds=time.perf_counter() - start_time,
        )

    try:
        with Image.open(media_path) as image:
            text = pytesseract.image_to_string(
                image, lang=languages or CONFIG.ocr.languages
            )
    except Exception as exc:
        logger.warning(f"OCR failed for {media_path}: {exc}")
        return OCRResult(
            text="",
            status="failed",
            error=str(exc),
            duration_seconds=time.perf_counter() - start_time,
        )

    return OCRResult(
        text=text.strip(),
        status="completed",
        duration_seconds=time.perf_counter() - start_time,
    )


def generate_caption_from_text(text: str, target_lang: str) -> str:
    """Generate a translated caption suggestion from OCR text."""

    normalized_text = text.strip()
    if not normalized_text:
        return ""

    if not CONFIG.gemini.api_key:
        return ""
    api_key = CONFIG.gemini.api_key.get_secret_value()
    if not api_key or not genai:
        return ""

    model_name = CONFIG.gemini.model
    prompt = (
        f"Translate the following text to {target_lang} "
        f"and suggest a concise caption:\n{normalized_text}"
    )
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return (getattr(response, "text", "") or "").strip()
    except Exception:
        logger.exception("Gemini caption generation failed")
        return ""


def generate_caption(
    media_path: str, target_lang: str, languages: str | None = None
) -> str:
    """Extract OCR text and generate a caption suggestion from it."""

    result = extract_ocr_text(media_path, languages=languages)
    if result.status != "completed" or not result.text:
        return ""
    return generate_caption_from_text(result.text, target_lang)
