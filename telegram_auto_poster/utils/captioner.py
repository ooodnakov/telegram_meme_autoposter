from __future__ import annotations

import base64
import os
from typing import List

from loguru import logger

DEFAULT_CAPTIONS = [
    "Отличный мем!",
    "Подписывайтесь на канал!",
    "Как вам такой мем?",
]


async def generate_captions(image_path: str, n: int = 3) -> List[str]:
    """Generate caption suggestions using OpenAI API.

    If ``OPENAI_API_KEY`` is not configured, fallback captions are returned.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(image_path)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set, using fallback captions")
        return DEFAULT_CAPTIONS[:n]

    import openai

    try:
        client = openai.AsyncOpenAI(api_key=api_key)
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Предложи короткие варианты подписи к изображению для Telegram-канала."
                            " Ответь списком из нескольких фраз.",
                        },
                        {
                            "type": "image_url",
                            "image_url": f"data:image/jpeg;base64,{b64}",
                        },
                    ],
                }
            ],
            max_tokens=100,
        )
        text = response.choices[0].message.content or ""
        captions = [c.strip("- \n") for c in text.split("\n") if c.strip()]
        return captions[:n] if captions else DEFAULT_CAPTIONS[:n]
    except (
        openai.APIError,
        openai.RateLimitError,
        openai.AuthenticationError,
    ) as e:
        logger.error(f"OpenAI error: {e}")
        return DEFAULT_CAPTIONS[:n]
    except Exception as e:  # pragma: no cover - network errors
        logger.error(f"Unexpected error: {e}")
        return DEFAULT_CAPTIONS[:n]
