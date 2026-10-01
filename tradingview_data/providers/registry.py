"""The providers this server offers, in dropdown order. Register new providers here."""

from __future__ import annotations

from .alphavantage import AlphaVantage
from .base import ProviderRegistry
from .marketstack import Marketstack


def default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(AlphaVantage())
    registry.register(Marketstack())
    return registry
