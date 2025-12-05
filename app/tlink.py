"""Helpers for interacting with TLINK cloud services."""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

import requests
from flask import current_app


class TLinkOAuthClient:
    """Very small OAuth token cache with automatic refresh."""

    def __init__(self, config: Dict[str, Any]):
        self._config = config
        self._lock = threading.RLock()
        self._access_token: Optional[str] = None
        self._token_type: str = "Bearer"
        self._expires_at: float = 0.0

    def get_authorization_header(self) -> str:
        token = self._ensure_token()
        token_type = self._token_type or "Bearer"
        return f"{token_type} {token}"

    def invalidate_token(self) -> None:
        with self._lock:
            self._access_token = None
            self._expires_at = 0.0

    def _ensure_token(self) -> str:
        with self._lock:
            if self._access_token and not self._is_expired():
                return self._access_token

            self._refresh_token()
            if not self._access_token:
                raise RuntimeError("Unable to obtain TLINK access token")
            return self._access_token

    def _is_expired(self) -> bool:
        buffer_seconds = self._config.get("TLINK_OAUTH_REFRESH_BUFFER", 60)
        return time.time() >= max(0.0, self._expires_at - buffer_seconds)

    def _refresh_token(self) -> None:
        url = self._config.get("TLINK_OAUTH_TOKEN_URL")
        client_id = self._config.get("TLINK_OAUTH_CLIENT_ID")
        client_secret = self._config.get("TLINK_OAUTH_CLIENT_SECRET")
        username = self._config.get("TLINK_OAUTH_USERNAME")
        password = self._config.get("TLINK_OAUTH_PASSWORD")
        scope = self._config.get("TLINK_OAUTH_SCOPE")
        timeout = self._config.get("TLINK_HTTP_TIMEOUT", 30)

        missing = [
            name
            for name, value in [
                ("TLINK_OAUTH_TOKEN_URL", url),
                ("TLINK_OAUTH_CLIENT_ID", client_id),
                ("TLINK_OAUTH_CLIENT_SECRET", client_secret),
                ("TLINK_OAUTH_USERNAME", username),
                ("TLINK_OAUTH_PASSWORD", password),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Missing TLINK OAuth settings: " + ", ".join(missing)
            )

        data = {
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        if scope:
            data["scope"] = scope

        response = requests.post(
            url,
            data=data,
            auth=(client_id, client_secret),
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()

        access_token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        token_type = payload.get("token_type") or payload.get("tokenType")

        if not access_token:
            raise RuntimeError("TLINK token response missing access_token")

        self._access_token = access_token
        if token_type:
            self._token_type = token_type
        self._expires_at = time.time() + max(expires_in, 0)


def get_oauth_client():
    app = current_app._get_current_object()
    client = app.extensions.get("tlink_oauth_client")
    if client is None:
        client = TLinkOAuthClient(app.config)
        app.extensions["tlink_oauth_client"] = client
    return client