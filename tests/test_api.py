"""Tests for the VCVideo NVR API client."""

from __future__ import annotations

import aiohttp
import pytest

from custom_components.vcvideo_nvr.api import (
    SNAPSHOT_ENDPOINTS,
    VCVideoAuthError,
    VCVideoConnectionError,
    VCVideoNVRClient,
    channel_to_number,
    looks_like_image,
)
from custom_components.vcvideo_nvr.const import STREAM_TYPE_MAIN, STREAM_TYPE_SUB

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 1024
HTML = b"<html><body>404 Not Found</body></html>" * 40


class FakeResponse:
    """Minimal stand-in for an aiohttp response."""

    def __init__(
        self,
        status: int = 200,
        json_body: object | None = None,
        headers: dict[str, str] | None = None,
        payload: bytes = b"",
    ) -> None:
        self.status = status
        self.headers = headers or {}
        self._json = json_body
        self._payload = payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)

    async def json(self, content_type: str | None = None) -> object:
        return self._json

    async def read(self) -> bytes:
        return self._payload


class FakeCookieJar:
    """Cookie jar that only needs to be clearable."""

    def clear(self) -> None:
        """Discard all cookies."""


class FakeSession:
    """Records requests and replays canned responses."""

    closed = False

    def __init__(self, responses: object) -> None:
        self._responses = responses
        self.cookie_jar = FakeCookieJar()
        self.requests: list[str] = []

    def _next(self, url: str):
        self.requests.append(url)
        if callable(self._responses):
            return self._responses(url)
        if isinstance(self._responses, list):
            return self._responses.pop(0)
        return self._responses

    def post(self, url: str, **_kwargs: object):
        return self._next(url)

    def get(self, url: str, **_kwargs: object):
        return self._next(url)

    async def close(self) -> None:
        self.closed = True


def make_client(session: FakeSession | None = None, password: str = "testpass"):
    """Return a client wired to a fake session."""
    client = VCVideoNVRClient(
        host="192.168.0.20",
        username="admin",
        password=password,
        port=80,
        rtsp_port=554,
    )
    if session is not None:
        client._session = session  # noqa: SLF001
    return client


@pytest.fixture
def client():
    """Return a bare client."""
    return make_client()


@pytest.mark.parametrize(
    ("channel_id", "expected"),
    [
        ("IP_CH1", 1),
        ("IP_CH12", 12),
        ("CH3", 3),
        ("01", 1),
        ("", 7),
        ("no-digits", 7),
    ],
)
def test_channel_to_number(channel_id: str, expected: int) -> None:
    """Channel ids of every firmware flavour map onto a channel number."""
    assert channel_to_number(channel_id, 7) == expected


@pytest.mark.parametrize(
    ("content_type", "payload", "expected"),
    [
        ("image/jpeg", JPEG, True),
        ("text/html", JPEG, True),  # magic bytes win over a wrong content type
        ("image/jpeg", HTML, False),  # an HTML error page is not an image
        ("image/jpeg", b"", False),
        ("image/jpeg", None, False),
        ("image/jpeg", b"\xff\xd8\xff", False),  # too small to be a frame
    ],
)
def test_looks_like_image(content_type, payload, expected) -> None:
    """Only real image payloads are accepted as snapshots."""
    assert looks_like_image(content_type, payload) is expected


def test_build_rtsp_url(client: VCVideoNVRClient) -> None:
    """Main and sub stream URLs follow the NVR's channel pattern."""
    assert (
        client.build_rtsp_url(1, STREAM_TYPE_MAIN)
        == "rtsp://admin:testpass@192.168.0.20:554/ch01/0"
    )
    assert (
        client.build_rtsp_url(12, STREAM_TYPE_SUB)
        == "rtsp://admin:testpass@192.168.0.20:554/ch12/1"
    )


def test_build_rtsp_url_encodes_credentials() -> None:
    """A password with URL metacharacters must not corrupt the RTSP URL."""
    client = make_client(password="p@ss:word/1 2")
    url = client.build_rtsp_url(2)
    assert url == "rtsp://admin:p%40ss%3Aword%2F1%202@192.168.0.20:554/ch02/0"
    assert url.count("@") == 1


@pytest.mark.asyncio
async def test_login_reads_token_from_header() -> None:
    """The CSRF token is returned in the X-csrftoken response header."""
    session = FakeSession(
        FakeResponse(
            json_body={"result": "success", "data": {}},
            headers={"X-csrftoken": "abc123"},
        )
    )
    client = make_client(session)
    await client.async_login()
    assert client._token == "abc123"  # noqa: SLF001


@pytest.mark.asyncio
async def test_login_falls_back_to_token_in_body() -> None:
    """Older firmwares return the token in the JSON body instead."""
    session = FakeSession(
        FakeResponse(json_body={"result": "success", "data": {"token": "body-token"}})
    )
    client = make_client(session)
    await client.async_login()
    assert client._token == "body-token"  # noqa: SLF001


@pytest.mark.asyncio
async def test_login_without_token_fails() -> None:
    """A login that yields no token is not a usable session."""
    session = FakeSession(FakeResponse(json_body={"result": "success", "data": {}}))
    client = make_client(session)
    with pytest.raises(VCVideoAuthError):
        await client.async_login()


@pytest.mark.asyncio
async def test_login_invalid_credentials() -> None:
    """A failed login reports an auth error, not a connection error."""
    session = FakeSession(
        FakeResponse(json_body={"result": "failed", "error_code": "login_failed"})
    )
    client = make_client(session)
    with pytest.raises(VCVideoAuthError):
        await client.async_login()


@pytest.mark.asyncio
async def test_login_unauthorized_status() -> None:
    """HTTP 401 from digest auth is an auth error."""
    session = FakeSession(FakeResponse(status=401))
    client = make_client(session)
    with pytest.raises(VCVideoAuthError):
        await client.async_login()


@pytest.mark.asyncio
async def test_connection_error() -> None:
    """Transport failures surface as connection errors."""

    def raise_connect(_url: str):
        raise aiohttp.ClientConnectorError(None, OSError())

    client = make_client(FakeSession(raise_connect))
    with pytest.raises(VCVideoConnectionError):
        await client.async_login()


@pytest.mark.asyncio
async def test_expired_session_raises_auth_error() -> None:
    """An expired session is reported with HTTP 200 and an error code."""
    session = FakeSession(
        FakeResponse(json_body={"result": "failed", "error_code": "invalid_session"})
    )
    client = make_client(session)
    with pytest.raises(VCVideoAuthError):
        await client.async_get_channel_info()


@pytest.mark.asyncio
async def test_get_channel_info_items_wrapper() -> None:
    """Channels wrapped in channel_param.items are returned."""
    session = FakeSession(
        FakeResponse(
            json_body={
                "result": "success",
                "data": {"channel_param": {"items": [{"channel": "IP_CH1"}, "junk"]}},
            }
        )
    )
    client = make_client(session)
    assert await client.async_get_channel_info() == [{"channel": "IP_CH1"}]


@pytest.mark.asyncio
async def test_get_channel_info_plain_list() -> None:
    """Firmwares that return channel_param as a list also work."""
    session = FakeSession(
        FakeResponse(
            json_body={
                "result": "success",
                "data": {"channel_param": [{"channel": "IP_CH2"}]},
            }
        )
    )
    client = make_client(session)
    assert await client.async_get_channel_info() == [{"channel": "IP_CH2"}]


@pytest.mark.asyncio
async def test_snapshot_probe_finds_endpoint() -> None:
    """The first endpoint returning a real image is remembered."""
    expected = next(e for e in SNAPSHOT_ENDPOINTS if "webcapture" in e)

    def respond(url: str):
        if "webcapture" in url:
            return FakeResponse(headers={"Content-Type": "image/jpeg"}, payload=JPEG)
        return FakeResponse(status=404)

    client = make_client(FakeSession(respond))
    endpoint = await client.async_probe_snapshot_endpoint("IP_CH1", 1)
    assert endpoint == expected
    assert client.snapshot_endpoint == expected
    assert await client.async_get_snapshot("IP_CH1", 1) == JPEG


@pytest.mark.asyncio
async def test_snapshot_probe_rejects_error_pages() -> None:
    """An HTML error page served with HTTP 200 is not a snapshot."""
    session = FakeSession(
        lambda _url: FakeResponse(headers={"Content-Type": "image/jpeg"}, payload=HTML)
    )
    client = make_client(session)
    assert await client.async_probe_snapshot_endpoint("IP_CH1", 1) is None
    assert client.snapshot_probed is True
    # Every candidate was tried exactly once, then the result is cached.
    assert len(session.requests) == len(SNAPSHOT_ENDPOINTS)
    assert await client.async_get_snapshot("IP_CH1", 1) is None
    assert len(session.requests) == len(SNAPSHOT_ENDPOINTS)


@pytest.mark.asyncio
async def test_snapshot_without_probe_does_not_probe() -> None:
    """Thumbnail requests never trigger the slow endpoint probe."""
    session = FakeSession(lambda _url: FakeResponse(status=404))
    client = make_client(session)
    assert await client.async_get_snapshot("IP_CH1", 1, probe=False) is None
    assert session.requests == []


@pytest.mark.asyncio
async def test_snapshot_url_never_leaks_unencoded_password() -> None:
    """Credentials embedded in snapshot URLs are percent-encoded."""
    client = make_client(password="p@ss word")
    url = client._snapshot_url(  # noqa: SLF001
        "/cgi-bin/snapshot.cgi?chn={n0}&u={user}&p={password}", "IP_CH1", 1
    )
    assert "p%40ss%20word" in url
    assert "p@ss word" not in url
