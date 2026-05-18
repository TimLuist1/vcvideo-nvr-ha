"""VCVideo NVR API client."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import ClientSession

from .const import (
    API_CHANNEL_INFO,
    API_DEVICE_INFO,
    API_HEARTBEAT,
    API_LOGIN,
    API_LOGIN_RANGE,
    API_LOGOUT,
    API_STREAM_URL,
    API_SYSTEM_BASE,
    API_VERSION,
    FIELD_DATA,
    FIELD_ERROR_CODE,
    FIELD_RESULT,
    FIELD_TOKEN,
    FIELD_VERSION,
    HEADER_TOKEN,
    STREAM_TYPE_MAIN,
    STREAM_TYPE_SUB,
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
        session: ClientSession | None = None,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._rtsp_port = rtsp_port
        self._username = username
        self._password = password
        self._session = session
        self._token: str | None = None
        self._owns_session = session is None

    @property
    def base_url(self) -> str:
        """Return base URL."""
        return f"http://{self._host}:{self._port}"

    async def _ensure_session(self) -> ClientSession:
        """Ensure an aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def _request(
        self,
        method: str,
        path: str,
        data: dict | None = None,
        auth: aiohttp.DigestAuth | None = None,
    ) -> dict:
        """Make an authenticated request to the NVR API."""
        session = await self._ensure_session()
        url = f"{self.base_url}{path}?{self._timestamp()}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers[HEADER_TOKEN] = self._token

        body: dict[str, Any] = {}
        if data is not None:
            body = {FIELD_VERSION: API_VERSION, FIELD_DATA: data}

        try:
            async with session.request(
                method,
                url,
                json=body if body else None,
                headers=headers,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ssl=False,
            ) as response:
                if response.status == 401:
                    raise VCVideoAuthError("Authentication failed (401)")
                response.raise_for_status()
                return await response.json(content_type=None)
        except aiohttp.ClientConnectorError as err:
            raise VCVideoConnectionError(f"Cannot connect to {self._host}") from err
        except aiohttp.ClientResponseError as err:
            raise VCVideoConnectionError(f"HTTP error: {err}") from err
        except asyncio.TimeoutError as err:
            raise VCVideoConnectionError(f"Timeout connecting to {self._host}") from err

    def _timestamp(self) -> str:
        """Return a cache-busting timestamp string."""
        import datetime
        return datetime.datetime.now().strftime("%Y-%m-%d@%H:%M:%S")

    async def async_login(self) -> None:
        """Authenticate with the NVR and store the CSRF token."""
        auth = aiohttp.DigestAuth(self._username, self._password)
        payload = {
            FIELD_VERSION: API_VERSION,
            FIELD_DATA: {
                "UserName": self._username,
                "PassWord": self._password,
            },
        }
        session = await self._ensure_session()
        url = f"{self.base_url}{API_LOGIN}?{self._timestamp()}"
        try:
            async with session.post(
                url,
                json=payload,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ssl=False,
            ) as response:
                if response.status == 401:
                    raise VCVideoAuthError("Invalid credentials")
                response.raise_for_status()
                result = await response.json(content_type=None)
        except aiohttp.ClientConnectorError as err:
            raise VCVideoConnectionError(f"Cannot connect to {self._host}") from err
        except asyncio.TimeoutError as err:
            raise VCVideoConnectionError(f"Timeout connecting to {self._host}") from err

        if result.get(FIELD_RESULT) != "success":
            error = result.get(FIELD_ERROR_CODE, "unknown")
            raise VCVideoAuthError(f"Login failed: {error}")

        data = result.get(FIELD_DATA, {})
        self._token = data.get(FIELD_TOKEN)
        _LOGGER.debug("Logged in to NVR at %s, token: %s", self._host, bool(self._token))

    async def async_logout(self) -> None:
        """Logout from the NVR."""
        try:
            await self._request("POST", API_LOGOUT, data={})
        except Exception:  # noqa: BLE001
            pass
        self._token = None

    async def async_heartbeat(self) -> bool:
        """Send heartbeat to keep session alive. Returns False if re-login needed."""
        try:
            result = await self._request("POST", API_HEARTBEAT, data={})
            return result.get(FIELD_RESULT) == "success"
        except VCVideoAuthError:
            return False

    async def async_get_device_info(self) -> dict:
        """Get NVR device information."""
        result = await self._request("POST", API_DEVICE_INFO, data={})
        return result.get(FIELD_DATA, {})

    async def async_get_channel_info(self) -> list[dict]:
        """Get list of camera channels."""
        result = await self._request("POST", API_CHANNEL_INFO, data={})
        data = result.get(FIELD_DATA, {})
        channel_param = data.get("channel_param", {})
        items = channel_param.get("items", [])
        return items

    async def async_get_stream_url(
        self, channel: str, stream_type: int = STREAM_TYPE_MAIN
    ) -> str | None:
        """Get RTSP stream URL for a channel."""
        try:
            result = await self._request(
                "POST",
                API_STREAM_URL,
                data={"channel": channel, "stream_type": stream_type},
            )
            data = result.get(FIELD_DATA, {})
            return data.get("url") or data.get("rtsp_url") or data.get("stream_url")
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not get stream URL via API for %s: %s", channel, err)
            return None

    def build_rtsp_url(self, channel_no: int, stream_type: int = STREAM_TYPE_MAIN) -> str:
        """Build a standard RTSP URL for the channel (fallback if API fails)."""
        stream_name = "main" if stream_type == STREAM_TYPE_MAIN else "sub"
        ch = str(channel_no).zfill(2)
        return (
            f"rtsp://{self._username}:{self._password}"
            f"@{self._host}:{self._rtsp_port}/stream/{ch}/{stream_name}"
        )

    async def async_get_snapshot(self, channel: str) -> bytes | None:
        """Get a snapshot image from a channel."""
        try:
            session = await self._ensure_session()
            url = (
                f"{self.base_url}/cgi-bin/snapshot.cgi"
                f"?channel={channel}&{self._timestamp()}"
            )
            headers: dict[str, str] = {}
            if self._token:
                headers[HEADER_TOKEN] = self._token
            async with session.get(
                url,
                headers=headers,
                auth=aiohttp.DigestAuth(self._username, self._password),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ssl=False,
            ) as response:
                if response.status == 200:
                    ct = response.headers.get("Content-Type", "")
                    if "image" in ct:
                        return await response.read()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Snapshot failed for channel %s: %s", channel, err)
        return None

    async def async_close(self) -> None:
        """Close the client session."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
