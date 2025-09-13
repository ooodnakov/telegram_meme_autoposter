"""Utilities for validating Telegram Login Widget data."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Mapping, MutableMapping


def _compute_hash(data: Mapping[str, str], token: str) -> str:
    """Return the HMAC-SHA256 hash for ``data`` using ``token``.

    The algorithm follows the steps documented in the Telegram Login Widget
    specification: the bot token is hashed with SHA256 and used as the secret
    key for calculating a HMAC over the ``data-check-string`` built from the
    sorted key/value pairs.
    """

    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret_key = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_telegram_login(
    payload: MutableMapping[str, str | int], bot_token: str, *, max_age: int = 86400
) -> bool:
    """Validate Telegram Login Widget ``payload`` using ``bot_token``.

    ``payload`` must contain ``hash`` and ``auth_date`` fields. The
    ``auth_date`` must be within ``max_age`` seconds of the current time. The
    remaining fields are used to build the ``data-check-string``. Returns
    ``True`` if the signature matches and the payload is fresh, ``False``
    otherwise.
    """

    data: dict[str, str] = {k: str(v) for k, v in payload.items()}
    received_hash = data.pop("hash", None)
    auth_date = data.get("auth_date")
    if received_hash is None or auth_date is None:
        return False
    try:
        if int(auth_date) < int(time.time()) - max_age:
            return False
    except ValueError:
        return False
    expected_hash = _compute_hash(data, bot_token)
    return hmac.compare_digest(expected_hash, received_hash)


def sign_telegram_data(payload: Mapping[str, str | int], bot_token: str) -> str:
    """Return a valid ``hash`` for ``payload``.

    This helper mirrors :func:`validate_telegram_login` but is intended for use
    in tests to craft a signed payload.
    """

    data = {k: str(v) for k, v in payload.items() if k != "hash"}
    return _compute_hash(data, bot_token)


__all__ = ["validate_telegram_login", "sign_telegram_data"]
