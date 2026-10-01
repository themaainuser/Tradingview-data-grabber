"""HTTP routes for data providers: list, catalog, query."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .base import ProviderRegistry


class QueryRequest(BaseModel):
    """Body of ``POST /api/providers/{id}/query``."""

    endpoint: str = Field(min_length=1, max_length=120)
    params: Dict[str, Union[str, List[str]]] = Field(default_factory=dict)
    refresh: bool = False


def register_provider_routes(app: FastAPI, registry: ProviderRegistry, respond: Callable[[Any], Response]) -> None:
    """Adds the provider routes. ``respond`` serialises a payload (the API's NaN-safe JSON response)."""

    def provider_or_404(provider_id: str) -> Any:
        try:
            return registry.get(provider_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="provider not found") from None

    @app.get("/api/providers")
    def list_providers() -> Response:
        """Every data provider this server offers, with whether its key is set (never the key)."""

        return respond({"providers": [p.summary() for p in registry.all()]})

    @app.get("/api/providers/{provider_id}/catalog")
    def provider_catalog(provider_id: str) -> Response:
        """The provider's endpoints with their parameters, premium flags and docs examples."""

        provider = provider_or_404(provider_id)
        return respond({"provider": provider.summary(), **provider.catalog()})

    @app.post("/api/providers/{provider_id}/query")
    def provider_query(provider_id: str, body: QueryRequest) -> Response:
        """Fetches one endpoint. Provider-side problems (limits, premium, bad key) are a 200 with a status."""

        provider = provider_or_404(provider_id)
        try:
            return respond(provider.query(body.endpoint, body.params, body.refresh))
        except KeyError:
            raise HTTPException(status_code=404, detail="endpoint not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
