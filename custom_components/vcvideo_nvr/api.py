"""VCVideo NVR API client."""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import Any
from urllib.parse import quote

import aiohttp
from aiohttp import ClientSession, DigestAuthMiddleware

from .const import (
    API_CHANNEL_INFO,
    API_DEVICE_INFO,
    API_HEARTBEAT,
    API_LOGIN,
    API_LOGOUT,
    API_VERSION,
    AUTH_ERROR_CODES,
    FIELD_DATA,
    FIELD_ERROR_CODE,
    FIELD_RESULT,
    FIELD_VERSION,
    HEADER_TOKEN,
    RESULT_SUCCESS,
    SNAPSHOT_PROBE_TIMEOUT,
    STREAM_TYPE_MAIN,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10

# Candidate HTTP still-image endpoints, tried once per NVR. Different OEM
# firmwares of this NVR platform ship different (or no) snapshot CGIs, so the
# working one is detected at runtime instead of hardcoded. Placeholders:
#   {ch}  raw channel id as reported by the NVR (e.g. "IP_CH1")
#   {n}   1-based channel number
#   {n0}  0-based channel number
#   {n2}  1-based channel number, zero padded to two digits
#   {user}/{password}  URL-encoded credentials
SNAPSHOT_ENDPOINTS: tuple[str, ...] = (
    "/cgi-bin/snapshot.cgi?chn={n0}&u={user}&p={password}",
    "/cgi-bin/snapshot.cgi?channel={n}",
    "/webcapture.jpg?command=snap&channel={n0}",
    "/Snapshot/{n}/RemoteImageCapture?ImageFormat=2",
    "/ISAPI/Streaming/channels/{n}01/picture",
    "/API/Web/Snapshot?channel={ch}",
    "/snapshot/ch{n2}",
)

# Enough bytes to be a real frame rather than a 1x1 placeholder or error page.
MIN_IMAGE_BYTES = 512

_IMAGE_MAGIC: tuple[bytes, ...] = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
)


def channel_to_number(channel_id: str, fallback: int) -> int:
    """Extract a numeric channel number from IDs like 'IP_CH1', '01', 'CH3'."""
    if not channel_id:
        return fallback
    match = re.search(r"(\d+)", str(channel_id))
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return fallback


def looks_like_image(content_type: str, payload: bytes | None) -> bool:
    """Return True if the payload is plausibly a still image.

    NVRs happily answer an unknown CGI path with HTTP 200 and an HTML error
    page, so the content type alone cannot be trusted.
    """
    if not payload or len(payload) < MIN_IMAGE_BYTES:
        return False
    if payload.startswith(_IMAGE_MAGIC):
        return True
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return True
    if not content_type.split(";")[0].strip().lower().startswith("image/"):
        return False
    # An unrecognised format is only trusted if it is not obviously an HTML or
    # JSON error body mislabelled as an image.
    return payload.lstrip()[:1] not in (b"<", b"{")


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
        self._snapshot_endpoint: str | None = None
        self._snapshot_probed = False
        self._snapshot_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Return HTTP base URL of the NVR."""
        return f"http://{self._host}:{self._port}"

    @property
    def snapshot_endpoint(self) -> str | None:
        """Return the detected HTTP snapshot endpoint template, if any."""
        return self._snapshot_endpoint

    @property
    def snapshot_probed(self) -> bool:
        """Return True once the HTTP snapshot endpoints have been probed."""
        return self._snapshot_probed

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

    @staticmethod
    def _check_result(result: Any, context: str) -> dict:
        """Validate an API response body and surface session expiry.

        The NVR reports an expired session with HTTP 200 and an error code in
        the body, so it has to be translated into VCVideoAuthError here for the
        coordinator to re-login.
        """
        if not isinstance(result, dict):
            raise VCVideoConnectionError(f"{context}: unexpected response {result!r}")
        if result.get(FIELD_RESULT) == RESULT_SUCCESS:
            return result
        error = str(result.get(FIELD_ERROR_CODE, "")).lower()
        if error in AUTH_ERROR_CODES:
            raise VCVideoAuthError(f"{context}: session invalid ({error})")
        if error:
            raise VCVideoConnectionError(f"{context} failed: {error}")
        # Some endpoints answer without a "result" field at all; treat the
        # payload as usable rather than failing the whole update.
        return result

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
                if response.status in (401, 403):
                    raise VCVideoAuthError(
                        f"Authentication failed ({response.status})"
                    )
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
        except aiohttp.ClientError as err:
            raise VCVideoConnectionError(f"Request to {self._host} failed: {err}") from err
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
                if response.status in (401, 403):
                    raise VCVideoAuthError("Invalid credentials")
                response.raise_for_status()
                token = response.headers.get(HEADER_TOKEN)
                result = await response.json(content_type=None)
        except aiohttp.ClientResponseError as err:
            raise VCVideoConnectionError(f"HTTP error: {err}") from err
        except aiohttp.ClientConnectorError as err:
            raise VCVideoConnectionError(f"Cannot connect to {self._host}") from err
        except aiohttp.ClientError as err:
            raise VCVideoConnectionError(f"Request to {self._host} failed: {err}") from err
        except asyncio.TimeoutError as err:
            raise VCVideoConnectionError(f"Timeout connecting to {self._host}") from err

        if not isinstance(result, dict) or result.get(FIELD_RESULT) != RESULT_SUCCESS:
            error = "unknown"
            if isinstance(result, dict):
                error = result.get(FIELD_ERROR_CODE, "unknown")
            raise VCVideoAuthError(f"Login failed: {error}")

        # Older firmwares return the token in the body instead of the header.
        if not token:
            body = result.get(FIELD_DATA)
            if isinstance(body, dict):
                token = body.get("token") or body.get("csrf_token")
        if not token:
            raise VCVideoAuthError("Login succeeded but no CSRF token was returned")

        self._token = str(token)
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
            self._check_result(result, "Heartbeat")
        except VCVideoAuthError:
            return False
        except VCVideoConnectionError:
            return True  # transient — don't force re-login
        return True

    async def async_get_device_info(self) -> dict:
        """Return NVR device information."""
        result = self._check_result(
            await self._request(API_DEVICE_INFO, data={}), "Device info"
        )
        data = result.get(FIELD_DATA)
        return data if isinstance(data, dict) else {}

    async def async_get_channel_info(self) -> list[dict]:
        """Return list of camera channels."""
        result = self._check_result(
            await self._request(API_CHANNEL_INFO, data={}), "Channel info"
        )
        data = result.get(FIELD_DATA)
        if not isinstance(data, dict):
            return []
        channel_param = data.get("channel_param")
        # Firmwares differ: some wrap the channels in {"items": [...]},
        # others return the list directly.
        if isinstance(channel_param, dict):
            items = channel_param.get("items", [])
        elif isinstance(channel_param, list):
            items = channel_param
        else:
            items = []
        return [item for item in items if isinstance(item, dict)]

    def build_rtsp_url(
        self, channel_no: int, stream_type: int = STREAM_TYPE_MAIN
    ) -> str:
        """Construct an RTSP URL for a channel.

        Pattern verified against the NVR's RTSP server (`Surveillance Server`):
            rtsp://user:pass@host:554/chNN/0   (main stream)
            rtsp://user:pass@host:554/chNN/1   (sub stream)

        Credentials are percent-encoded so passwords containing `@`, `:`, `/`
        or spaces do not corrupt the URL.
        """
        user = quote(self._username, safe="")
        password = quote(self._password, safe="")
        return (
            f"rtsp://{user}:{password}"
            f"@{self._host}:{self._rtsp_port}/ch{channel_no:02d}/{stream_type}"
        )

    def _snapshot_url(self, template: str, channel: str, channel_no: int) -> str:
        """Render a snapshot endpoint template into a full URL."""
        path = template.format(
            ch=quote(str(channel), safe=""),
            n=channel_no,
            n0=max(channel_no - 1, 0),
            n2=f"{channel_no:02d}",
            user=quote(self._username, safe=""),
            password=quote(self._password, safe=""),
        )
        separator = "&" if "?" in path else "?"
        return f"{self.base_url}{path}{separator}_={self._timestamp()}"

    async def _async_fetch_snapshot(
        self, template: str, channel: str, channel_no: int, timeout: int
    ) -> bytes | None:
        """Fetch a still image from one candidate endpoint."""
        session = await self._ensure_session()
        headers: dict[str, str] = {}
        if self._token:
            headers[HEADER_TOKEN] = self._token
        try:
            async with session.get(
                self._snapshot_url(template, channel, channel_no),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    return None
                payload = await response.read()
                content_type = response.headers.get("Content-Type", "")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            # Never log the rendered URL — some templates carry credentials.
            _LOGGER.debug("Snapshot %s failed for channel %s: %s", template, channel, err)
            return None
        if looks_like_image(content_type, payload):
            return payload
        return None

    async def async_probe_snapshot_endpoint(
        self, channel: str, channel_no: int
    ) -> str | None:
        """Find a working HTTP snapshot endpoint, once per NVR.

        Returns the endpoint template, or None if this NVR has no usable HTTP
        still-image CGI — in which case callers fall back to grabbing a frame
        from the RTSP stream.
        """
        async with self._snapshot_lock:
            if self._snapshot_probed:
                return self._snapshot_endpoint
            for template in SNAPSHOT_ENDPOINTS:
                image = await self._async_fetch_snapshot(
                    template, channel, channel_no, SNAPSHOT_PROBE_TIMEOUT
                )
                if image is not None:
                    _LOGGER.debug("NVR %s serves snapshots via %s", self._host, template)
                    self._snapshot_endpoint = template
                    break
            else:
                _LOGGER.info(
                    "NVR %s has no usable HTTP snapshot endpoint; "
                    "thumbnails will be grabbed from the RTSP stream",
                    self._host,
                )
            self._snapshot_probed = True
            return self._snapshot_endpoint

    async def async_get_snapshot(
        self, channel: str, channel_no: int, probe: bool = True
    ) -> bytes | None:
        """Fetch a still image over HTTP, or None if unsupported."""
        if not self._snapshot_probed:
            if not probe:
                return None
            await self.async_probe_snapshot_endpoint(channel, channel_no)
        if not self._snapshot_endpoint:
            return None
        image = await self._async_fetch_snapshot(
            self._snapshot_endpoint, channel, channel_no, REQUEST_TIMEOUT
        )
        if image is None:
            _LOGGER.debug(
                "HTTP snapshot for channel %s returned no image via %s",
                channel,
                self._snapshot_endpoint,
            )
        return image

    async def async_close(self) -> None:
        """Close the underlying aiohttp ClientSession."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
