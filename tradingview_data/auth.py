"""Authenticated TradingView session-token retrieval."""

from __future__ import annotations

import os
from typing import Any

import requests

SIGN_IN_URL = "https://www.tradingview.com/accounts/signin/"


def get_auth_token(username: str | None = None, password: str | None = None) -> str:
    """Retrieve an account token without logging or persisting credentials.

    Credentials default to ``TV_USERNAME`` and ``TV_PASSWORD``.  Callers should
    pass the returned token directly to a stream configuration or store it in a
    secret manager rather than a source-controlled file.
    """

    user = username or os.getenv("TV_USERNAME")
    secret = password or os.getenv("TV_PASSWORD")
    if not user or not secret:
        raise ValueError("TV_USERNAME and TV_PASSWORD must be set for authenticated access")

    try:
        with requests.Session() as session:
            response = session.post(
                SIGN_IN_URL,
                data={"username": user, "password": secret, "remember": "on"},
                headers={"Referer": "https://www.tradingview.com"},
                timeout=20,
            )
            response.raise_for_status()
            payload: Any = response.json()
    except requests.RequestException as exc:
        raise RuntimeError("unable to sign in to TradingView") from exc
    except ValueError as exc:
        raise RuntimeError("TradingView returned a non-JSON sign-in response") from exc

    token = payload.get("user", {}).get("auth_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise RuntimeError("TradingView sign-in response did not include an auth token")
    return token
