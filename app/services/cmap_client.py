"""Async client for the CMap v1 API (OAuth2 client-credentials).

Auth (per docs.cmaphq.com): POST the token endpoint with grant_type=
client_credentials, client_id/secret, scope=api_access and a resource param, then
send the bearer token on every call. Pagination shape varies by endpoint, so
`get_all` is tolerant — it unwraps the common envelopes and stops on a short page.

Time is read via time.monotonic() only for token-expiry caching.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Response envelope keys CMap-style APIs use to wrap a page of records.
_ITEM_KEYS = ("items", "data", "results", "value", "records")


class CmapError(RuntimeError):
    """A CMap API call failed (auth, HTTP, or unexpected response shape)."""


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Pull the record list out of a page response (array or wrapped object)."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in _ITEM_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


class CmapClient:
    """Holds a cached bearer token and fetches full (paged) list endpoints."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0

    async def _token_for(self, client: httpx.AsyncClient) -> str:
        if self._token and time.monotonic() < self._expires_at:
            return self._token
        if not settings.cmap_enabled:
            raise CmapError("CMAP_CLIENT_ID / CMAP_CLIENT_SECRET are not set")
        resp = await client.post(
            settings.cmap_token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.cmap_client_id,
                "client_secret": settings.cmap_client_secret,
                "scope": settings.cmap_scope,
                "resource": settings.cmap_resource,
            },
        )
        if resp.status_code != 200:
            raise CmapError(
                f"CMap token request failed ({resp.status_code}): {resp.text[:300]}"
            )
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise CmapError("CMap token response had no access_token")
        self._token = str(token)
        # Refresh a minute early to avoid using a token mid-expiry.
        self._expires_at = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return self._token

    async def get_all(
        self, path: str, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Every record from a v1 list endpoint (e.g. ``/v1/Users``). CMap v1 list
        endpoints return the FULL collection in one response — pagination params
        (page/skip/take/offset) are ignored — so this is a single GET. ``limit``
        slices the result for --limit / --dry-run sampling."""
        url = settings.cmap_base_url.rstrip("/") + path
        async with httpx.AsyncClient(timeout=60.0) as client:
            token = await self._token_for(client)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            # CMap resolves the account from this header, not the URL — without it
            # every /v1 call returns 403 "Unspecified Tenant".
            if settings.cmap_tenant_id:
                headers["tenant_id"] = settings.cmap_tenant_id
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                raise CmapError(
                    f"CMap GET {path} failed ({resp.status_code}): {resp.text[:300]}"
                )
            items = _extract_items(resp.json())
        return items[:limit] if limit is not None else items
