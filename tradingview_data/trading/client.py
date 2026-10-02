"""One guarded request to the Alpaca Trading API, for the paper or the live environment.

Paper and live are different hosts with different keys. The credentials are read from the
environment at call time, go only into request headers, and are scrubbed from everything that comes
back. Live trading is off until ``ALPACA_ENABLE_LIVE_TRADING`` is set, and live keys are never
read from the variables that paper falls back to, so a live key cannot be used by accident.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

from ..providers.common import HttpRequest, default_http_request

KEY_HEADER = "APCA-API-KEY-ID"
SECRET_HEADER = "APCA-API-SECRET-KEY"
DATA_URL = "https://data.alpaca.markets"
_TRUE = {"1", "true", "yes", "on"}
_MIN_SCRUBBED = 8  # shorter values would garble ordinary words and protect nothing


@dataclass(frozen=True)
class Environment:
    id: str
    label: str
    base_url: str
    real_money: bool
    key_env: str
    secret_env: str
    fallback_key_env: Optional[str] = None
    fallback_secret_env: Optional[str] = None
    enable_env: Optional[str] = None


PAPER = Environment(
    id="paper",
    label="Paper trading",
    base_url="https://paper-api.alpaca.markets",
    real_money=False,
    key_env="ALPACA_PAPER_API_KEY_ID",
    secret_env="ALPACA_PAPER_API_SECRET_KEY",
    fallback_key_env="ALPACA_API_KEY_ID",
    fallback_secret_env="ALPACA_API_SECRET_KEY",
)
LIVE = Environment(
    id="live",
    label="Live trading",
    base_url="https://api.alpaca.markets",
    real_money=True,
    key_env="ALPACA_LIVE_API_KEY_ID",
    secret_env="ALPACA_LIVE_API_SECRET_KEY",
    enable_env="ALPACA_ENABLE_LIVE_TRADING",
)
ENVIRONMENTS: dict[str, Environment] = {PAPER.id: PAPER, LIVE.id: LIVE}


@dataclass
class Outcome:
    """What one request came to. ``status`` is ``ok``, ``not_configured``, ``invalid_key``, ``rejected``,
    ``not_found``, ``rate_limited`` or ``upstream_error``. ``outcome_unknown`` is set when a request
    that changes something may have reached Alpaca although no answer came back."""

    status: str
    http_status: Optional[int] = None
    message: Optional[str] = None
    code: Optional[int] = None
    data: Any = None
    elapsed_ms: int = 0
    outcome_unknown: bool = False


def classify(http_status: int, payload: Any, auth_statuses: tuple[int, ...] = (401,)) -> tuple[str, Optional[int], Optional[str]]:
    """``(status, alpaca error code, alpaca's message)`` for one HTTP answer. The trading API answers 403
    for a refusal such as insufficient buying power, so only 401 means bad credentials there; the data API
    uses 403 for bad credentials too, so its callers pass both."""

    message = payload.get("message") if isinstance(payload, dict) and isinstance(payload.get("message"), str) else None
    code = payload.get("code") if isinstance(payload, dict) and isinstance(payload.get("code"), int) and not isinstance(payload.get("code"), bool) else None
    if 200 <= http_status < 300:
        return "ok", code, message
    if http_status in auth_statuses:
        return "invalid_key", code, message
    if http_status == 404:
        return "not_found", code, message
    if http_status == 429:
        return "rate_limited", code, message
    if http_status >= 500:
        return "upstream_error", code, message
    return "rejected", code, message


class TradingClient:
    def __init__(self, environment: Environment, http: Optional[HttpRequest] = None, getenv: Optional[Callable[[str], Optional[str]]] = None) -> None:
        self.environment = environment
        self._http = http or default_http_request
        self._getenv = getenv or os.environ.get

    # --- credentials ----------------------------------------------------------------------------

    def _value(self, name: Optional[str]) -> str:
        return (self._getenv(name) or "").strip() if name else ""

    def credentials(self) -> tuple[str, str]:
        """The key ID and secret, as one pair: the environment's own variables, else (paper only) the
        market-data pair. A key is never combined with a secret from another pair."""

        env = self.environment
        for key_name, secret_name in ((env.key_env, env.secret_env), (env.fallback_key_env, env.fallback_secret_env)):
            key, secret = self._value(key_name), self._value(secret_name)
            if key and secret:
                return key, secret
        return "", ""

    def configured(self) -> bool:
        return all(self.credentials())

    def enabled(self) -> bool:
        """Paper is always available; live only when ``ALPACA_ENABLE_LIVE_TRADING`` says so."""

        name = self.environment.enable_env
        return True if name is None else self._value(name).lower() in _TRUE

    def missing_message(self) -> str:
        env = self.environment
        names = f"{env.key_env} and {env.secret_env}"
        fallback = f" ({env.fallback_key_env} and {env.fallback_secret_env} also work)" if env.fallback_key_env else ""
        return f"No Alpaca {env.label.lower()} keys are set. Add {names}{fallback} to the backend's environment or .env file and restart it."

    # --- requests ---------------------------------------------------------------------------------

    def call(
        self,
        method: str,
        path: str,
        *,
        query: Optional[list[tuple[str, str]]] = None,
        body: Any = None,
        base_url: Optional[str] = None,
        auth_statuses: tuple[int, ...] = (401,),
    ) -> Outcome:
        """One request. Never raises: everything that can go wrong is an :class:`Outcome`."""

        key, secret = self.credentials()
        if not (key and secret):
            return Outcome("not_configured", message=self.missing_message())
        mutating = method.upper() != "GET"
        started = time.perf_counter()
        try:
            result = self._http(method.upper(), (base_url or self.environment.base_url) + path, query or [], body, {KEY_HEADER: key, SECRET_HEADER: secret})
        except requests.ConnectTimeout:
            return self._failed("Could not connect to Alpaca (timed out). Nothing was sent.", started)
        except requests.Timeout:
            return self._failed("Alpaca did not answer in time." + self._maybe_sent(mutating), started, mutating)
        except ValueError:
            return self._failed("Alpaca returned an unexpectedly large response." + self._maybe_sent(mutating), started, mutating)
        except requests.RequestException:
            return self._failed("Could not reach Alpaca (network error)." + self._maybe_sent(mutating), started, mutating)
        elapsed = int((time.perf_counter() - started) * 1000)
        text = result.body.decode("utf-8", errors="replace")
        for secret_value in (key, secret):
            if len(secret_value) >= _MIN_SCRUBBED:
                text = text.replace(secret_value, "***")
        payload: Any = None
        if text.strip():
            try:
                payload = json.loads(text)
            except ValueError:
                if 200 <= result.status < 300:
                    return Outcome("upstream_error", result.status, "Alpaca returned a response that could not be read." + self._maybe_sent(mutating), None, None, elapsed, mutating)
        status, code, message = classify(result.status, payload, auth_statuses)
        return Outcome(status, result.status, self._message(status, result.status, message), code, payload if status == "ok" else None, elapsed)

    @staticmethod
    def _maybe_sent(mutating: bool) -> str:
        return " The request may still have been processed: check the orders and positions before trying again." if mutating else ""

    @staticmethod
    def _failed(message: str, started: float, unknown: bool = False) -> Outcome:
        return Outcome("upstream_error", None, message, None, None, int((time.perf_counter() - started) * 1000), unknown)

    def _message(self, status: str, http_status: int, alpaca: Optional[str]) -> Optional[str]:
        label = self.environment.label.lower()
        if status == "ok":
            return None
        if status == "invalid_key":
            detail = f": {alpaca.rstrip('.')}" if alpaca else ""
            return f"Alpaca refused the credentials (HTTP {http_status}){detail}. Check that the key ID and secret belong to your {label} account: paper keys do not work for live trading, or the other way round."
        if status == "rate_limited":
            return f"Alpaca's rate limit was reached{f': {alpaca}' if alpaca else ''}. Wait a minute and try again."
        return alpaca.strip() if alpaca and alpaca.strip() else f"Alpaca answered with HTTP {http_status}."
