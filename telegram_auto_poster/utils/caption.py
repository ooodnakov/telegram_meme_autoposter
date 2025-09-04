"""Generate captions from media using OCR and Gemini API."""

from __future__ import annotations

from loguru import logger
from telegram_auto_poster.config import CONFIG


def generate_caption(media_path: str, target_lang: str) -> str:
    """Extract text via OCR and ask Gemini for a caption.

    Args:
        media_path: Path to the media file (image or video frame).
        target_lang: Target language code for translation.

    Returns:
        Suggested caption or an empty string on failure.
    """

    try:
        import pytesseract
        from PIL import Image
    except Exception as e:  # pragma: no cover - import failure
        logger.error(f"OCR dependencies missing: {e}")
        return ""

    try:
        text = pytesseract.image_to_string(Image.open(media_path))
    except Exception as e:
        logger.warning(f"OCR failed for {media_path}: {e}")
        return ""

    text = text.strip()
    if not text:
        return ""

    api_key = None
    model_name = ""
    try:
        api_key = CONFIG.gemini.api_key.get_secret_value()
        model_name = CONFIG.gemini.model
    except Exception:  # pragma: no cover - config error
        return ""
    if not api_key:
        return ""

    try:
        import google.generativeai as genai
    except Exception as e:  # pragma: no cover - import failure
        logger.error(f"Gemini client missing: {e}")
        return ""

    prompt = f"Translate the following text to {target_lang} and suggest a concise caption:\n{text}"
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(prompt)
        return (getattr(response, "text", "") or "").strip()
    except Exception as e:
        logger.warning(f"Gemini caption generation failed: {e}")
        return ""
