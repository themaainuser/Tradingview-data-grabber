"""The providers this server offers, in dropdown order. Register new providers here."""

from __future__ import annotations

from .alphavantage import AlphaVantage
from .base import ProviderRegistry


def default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(AlphaVantage())
    return registry
