"""Async Facebook Graph API client with dry-run support."""

import asyncio
import logging
import uuid
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.services.facebook.exceptions import (
    FacebookAuthError,
    FacebookConfigError,
    FacebookError,
    FacebookRateLimitError,
    redact_token_text,
)

logger = logging.getLogger("pod-automation")

_RETRYABLE_GRAPH_CODES = {4, 17, 32, 613}
_MAX_RETRIES = 2
_BACKOFF_SECONDS = (1.0, 2.0)


class FacebookClient(httpx.AsyncClient):
    """Thin async wrapper around the Facebook Graph API."""

    def __init__(
        self,
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
        graph_version: Optional[str] = None,
        dry_run: Optional[bool] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        """Resolve credentials from args or settings; never log the token."""
        settings = get_settings()
        self.page_id: str = page_id or settings.FACEBOOK_PAGE_ID
        self._token: str = access_token or settings.FACEBOOK_PAGE_ACCESS_TOKEN
        self.graph_version: str = graph_version or settings.FACEBOOK_GRAPH_VERSION
        self.dry_run: bool = settings.FACEBOOK_DRY_RUN if dry_run is None else dry_run
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
        super().__init__(
            base_url=f"https://graph.facebook.com/{self.graph_version}",
            timeout=timeout,
            transport=transport,
        )

    def _auth_params(self) -> dict[str, str]:
        """Return request params carrying the token (never logged)."""
        return {"access_token": self._token}

    def _parse_response(self, response: httpx.Response, action: str) -> dict[str, Any]:
        """Parse a Graph response into data or a typed FacebookError."""
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code < 400:
            return data if isinstance(data, dict) else {}
        error = data.get("error", {}) if isinstance(data, dict) else {}
        code = error.get("code")
        message = redact_token_text(
            error.get("message") or f"Graph API {action} failed ({response.status_code})."
        )
        if code == 190:
            raise FacebookAuthError(message, code=code)
        if response.status_code == 429 or code in _RETRYABLE_GRAPH_CODES:
            raise FacebookRateLimitError(message, code=code)
        if 500 <= response.status_code < 600:
            raise FacebookError(message, code=code, retryable=True)
        raise FacebookError(message, code=code, retryable=False)

    async def _request(
        self, method: str, path: str, params: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Send a request with retries for network errors, 429 and 5xx."""
        last_error: Optional[FacebookError] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = await super().request(method, path, params=params)
            except httpx.HTTPError as exc:
                last_error = FacebookError(
                    f"Network error during {path}: {type(exc).__name__}",
                    retryable=True,
                )
            else:
                try:
                    return self._parse_response(response, path)
                except FacebookRateLimitError as exc:
                    last_error = exc
                except FacebookError as exc:
                    if not exc.retryable:
                        raise
                    last_error = exc
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BACKOFF_SECONDS[attempt])
        assert last_error is not None
        raise last_error

    async def verify_token(self) -> dict[str, str]:
        """Verify the token and confirm it belongs to the configured Page."""
        if self.dry_run:
            return {
                "page_id": self.page_id or "dryrun",
                "page_name": "Dry Run Page",
            }
        if not self.page_id or not self._token:
            raise FacebookConfigError("Facebook Page ID and access token are required.")
        params = {"fields": "id,name"}
        params.update(self._auth_params())
        data = await self._request("GET", "/me", params=params)
        if str(data.get("id")) != str(self.page_id):
            raise FacebookConfigError(
                "The access token does not belong to the configured Page."
            )
        return {
            "page_id": str(data.get("id")),
            "page_name": str(data.get("name") or ""),
        }

    async def publish_text(
        self, message: str, link: Optional[str] = None
    ) -> dict[str, str]:
        """Publish a text post to the Page feed."""
        if self.dry_run:
            return {"id": "dryrun_" + uuid.uuid4().hex}
        if not self.page_id or not self._token:
            raise FacebookConfigError("Facebook Page ID and access token are required.")
        params: dict[str, Any] = {"message": message}
        if link:
            params["link"] = link
        params.update(self._auth_params())
        data = await self._request("POST", f"/{self.page_id}/feed", params=params)
        if "id" not in data:
            raise FacebookError("Graph API did not return a post id.")
        return {"id": str(data["id"])}

    async def publish_photo(self, image_url: str, caption: str) -> dict[str, str]:
        """Publish a photo post with a caption to the Page."""
        if self.dry_run:
            return {"id": "dryrun_" + uuid.uuid4().hex}
        if not self.page_id or not self._token:
            raise FacebookConfigError("Facebook Page ID and access token are required.")
        params: dict[str, Any] = {"url": image_url, "caption": caption}
        params.update(self._auth_params())
        data = await self._request("POST", f"/{self.page_id}/photos", params=params)
        if "id" not in data:
            raise FacebookError("Graph API did not return a photo post id.")
        return {"id": str(data["id"])}
