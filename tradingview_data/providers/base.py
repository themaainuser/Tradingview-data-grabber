"""What every data provider supplies, and a registry the API serves them from.

Adding a provider is one module plus one ``registry.register(...)`` call: implement
:class:`Provider`, return a catalog in the shape documented in ``alphavantage.py`` and normalise
query results to the view types in ``views.py``. The API and the frontend need no change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Union

Params = Mapping[str, Union[str, list[str]]]


@dataclass(frozen=True)
class Plan:
    """One subscription tier. A provider with tiers lists them cheapest first."""

    name: str
    summary: str


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    description: str
    website: str
    docs_url: str
    key_env: str
    key_url: Optional[str]
    limits_note: str
    plans: tuple[Plan, ...] = ()


class Provider(ABC):
    """One external data source with a catalog of endpoints and a way to query them."""

    info: ProviderInfo
    requests_this_session: int = 0

    @abstractmethod
    def configured(self) -> bool:
        """True when this provider's API key is present in the environment."""

    @abstractmethod
    def catalog(self) -> dict[str, Any]:
        """``{"categories": [...], "endpoints": [...]}`` as in the providers contract."""

    @abstractmethod
    def query(self, endpoint_id: str, params: Params, refresh: bool = False) -> dict[str, Any]:
        """Validate ``params``, call the provider and return a ``QueryResponse``.

        Raises ``KeyError`` for an unknown endpoint and ``ValueError`` (with a plain message) for
        invalid parameters. Everything that goes wrong at the provider is a response status.
        """

    def summary(self) -> dict[str, Any]:
        catalog = self.catalog()
        endpoints = catalog["endpoints"]
        return {
            "id": self.info.id,
            "name": self.info.name,
            "description": self.info.description,
            "website": self.info.website,
            "docs_url": self.info.docs_url,
            "key_env": self.info.key_env,
            "key_url": self.info.key_url,
            "configured": self.configured(),
            "endpoint_count": len(endpoints),
            "premium_count": sum(1 for endpoint in endpoints if endpoint["premium"]),
            "limits_note": self.info.limits_note,
            "plans": [asdict(plan) for plan in self.info.plans],
            "requests_this_session": self.requests_this_session,
        }


class ProviderRegistry:
    """Providers by id, in registration order (the order of the frontend dropdown)."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        if provider.info.id in self._providers:
            raise ValueError(f"provider {provider.info.id!r} is already registered")
        self._providers[provider.info.id] = provider

    def get(self, provider_id: str) -> Provider:
        return self._providers[provider_id]

    def all(self) -> list[Provider]:
        return list(self._providers.values())
