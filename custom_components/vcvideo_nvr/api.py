"""VCVideo NVR API client."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

import aiohttp
from aiohttp import ClientSession, DigestAuthMiddleware

from .const import (
    API_CHANNEL_INFO,
    API_DEVICE_INFO,
    API_HEARTBEAT,
    API_LOGIN,
    API_LOGOUT,
    API_VERSION,
    FIELD_DATA,
    FIELD_ERROR_CODE,
    FIELD_RESULT,
    FIELD_VERSION,
    HEADER_TOKEN,
    STREAM_TYPE_MAIN,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10


class VCVideoAuthError(Exception):
    """Authentication failed."""


class VCVideoConnectionError(Exception):
    """Cannot connect to NVR."""


class VCVideoNVRClient:
    """Client for the VCVideo NVR HTTP API."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 80,
        rtsp_port: int = 554,
    ) -> None:
        """Initialize the client.

        Note: a dedicated aiohttp ClientSession is created so we can attach the
        DigestAuthMiddleware and use the cookie jar for the NVR session cookie.
        """
        self._host = host
        self._port = port
        self._rtsp_port = rtsp_port
        self._username = username
        self._password = password
        self._token: str | None = None
        self._session: ClientSession | None = None

    @property
    def base_url(self) -> str:
        """Return HTTP base URL of the NVR."""
        return f"http://{self._host}:{self._port}"

    async def _ensure_session(self) -> ClientSession:
        """Lazily create the aiohttp ClientSession with DigestAuthMiddleware."""
        if self._session is None or self._session.closed:
            middleware = DigestAuthMiddleware(
                login=self._username, password=self._password
            )
            self._session = ClientSession(middlewares=(middleware,))
        return self._session

    @staticmethod
    def _timestamp() -> str:
        """Return a cache-busting timestamp string used by the NVR web UI."""
        return datetime.datetime.now().strftime("%Y-%m-%d@%H:%M:%S")

    async def _request(
        self,
        path: str,
        data: dict | None = None,
    ) -> dict:
        """POST a JSON request to the NVR API.

        The NVR API expects:
          - POST with JSON body {"version": "1.0", "data": {...}}
          - HTTP Digest auth (handled by the session middleware)
          - X-csrftoken header on every request after login
          - Session cookie (handled automatically by the aiohttp cookie jar)
        """
        session = await self._ensure_session()
        url = f"{self.base_url}{path}?{self._timestamp()}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers[HEADER_TOKEN] = self._token

        body = {FIELD_VERSION: API_VERSION, FIELD_DATA: data or {}}

        try:
            async with session.post(
                url,
                json=body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status == 401:
                    raise VCVideoAuthError("Authentication failed (401)")
                response.raise_for_status()
                # The NVR may rotate the CSRF token; pick up new one if present.
                new_token = response.headers.get(HEADER_TOKEN)
                if new_token:
                    self._token = new_token
                return await response.json(content_type=None)
        except aiohttp.ClientConnectorError as err:
            raise VCVideoConnectionError(f"Cannot connect to {self._host}") from err
        except aiohttp.ClientResponseError as err:
            raise VCVideoConnectionError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError as err:
            raise VCVideoConnectionError(f"Timeout connecting to {self._host}") from err

    async def async_login(self) -> None:
        """Authenticate with the NVR and store the CSRF token.

        The NVR returns the CSRF token in the response header `X-csrftoken`
        (NOT in the JSON body). A session cookie is also set.
        """
        session = await self._ensure_session()
        # Clear any stale session cookies before login.
        session.cookie_jar.clear()
        self._token = None

        url = f"{self.base_url}{API_LOGIN}?{self._timestamp()}"
        payload = {
            FIELD_VERSION: API_VERSION,
            FIELD_DATA: {
                "UserName": self._username,
                "PassWord": self._password,
            },
        }
        try:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status == 401:
                    raise VCVideoAuthError("Invalid credentials")
                response.raise_for_status()
                self._token = response.headers.get(HEADER_TOKEN)
                result = await response.json(content_type=None)
        except aiohttp.ClientConnectorError as err:
            raise VCVideoConnectionError(f"Cannot connect to {self._host}") from err
        except asyncio.TimeoutError as err:
            raise VCVideoConnectionError(f"Timeout connecting to {self._host}") from err

        if result.get(FIELD_RESULT) != "success":
            error = result.get(FIELD_ERROR_CODE, "unknown")
            raise VCVideoAuthError(f"Login failed: {error}")

        if not self._token:
            raise VCVideoAuthError("Login succeeded but no X-csrftoken header returned")

        _LOGGER.debug("Logged in to NVR at %s", self._host)

    async def async_logout(self) -> None:
        """Logout from the NVR (best-effort)."""
        try:
            await self._request(API_LOGOUT, data={})
        except Exception:  # noqa: BLE001
            pass
        self._token = None

    async def async_heartbeat(self) -> bool:
        """Send heartbeat. Returns False if session is no longer valid."""
        try:
            result = await self._request(API_HEARTBEAT, data={})
            return result.get(FIELD_RESULT) == "success"
        except VCVideoAuthError:
            return False
        except VCVideoConnectionError:
            return True  # transient — don't force re-login

    async def async_get_device_info(self) -> dict:
        """Return NVR device information."""
        result = await self._request(API_DEVICE_INFO, data={})
        return result.get(FIELD_DATA, {})

    async def async_get_channel_info(self) -> list[dict]:
        """Return list of camera channels."""
        result = await self._request(API_CHANNEL_INFO, data={})
        data = result.get(FIELD_DATA, {})
        channel_param = data.get("channel_param", {})
        return channel_param.get("items", [])

    def build_rtsp_url(
        self, channel_no: int, stream_type: int = STREAM_TYPE_MAIN
    ) -> str:
        """Construct an RTSP URL for a channel.

        Pattern verified against the NVR's RTSP server (`Surveillance Server`):
            rtsp://user:pass@host:554/chNN/0   (main stream)
            rtsp://user:pass@host:554/chNN/1   (sub stream)
        """
        return (
            f"rtsp://{self._username}:{self._password}"
            f"@{self._host}:{self._rtsp_port}/ch{channel_no:02d}/{stream_type}"
        )

    async def async_get_snapshot(self, channel: str) -> bytes | None:
        """Fetch a still image from the channel (best-effort)."""
        session = await self._ensure_session()
        url = (
            f"{self.base_url}/cgi-bin/snapshot.cgi"
            f"?channel={channel}&{self._timestamp()}"
        )
        headers: dict[str, str] = {}
        if self._token:
            headers[HEADER_TOKEN] = self._token
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status == 200:
                    ct = response.headers.get("Content-Type", "")
                    if "image" in ct:
                        return await response.read()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Snapshot failed for channel %s: %s", channel, err)
        return None

    async def async_close(self) -> None:
        """Close the underlying aiohttp ClientSession."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

