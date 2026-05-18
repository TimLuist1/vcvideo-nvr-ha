"""Tests for VCVideo NVR API client."""

from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from custom_components.vcvideo_nvr.api import (
    VCVideoAuthError,
    VCVideoConnectionError,
    VCVideoNVRClient,
)
from custom_components.vcvideo_nvr.const import STREAM_TYPE_MAIN


@pytest.fixture
def client():
    return VCVideoNVRClient(
        host="192.168.0.20",
        username="admin",
        password="testpass",
        port=80,
        rtsp_port=554,
    )


def test_build_rtsp_url(client):
    url = client.build_rtsp_url(1, STREAM_TYPE_MAIN)
    assert "rtsp://" in url
    assert "192.168.0.20" in url
    assert "554" in url


@pytest.mark.asyncio
async def test_login_success(client):
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "result": "success",
            "data": {"token": "abc123", "last_login_time": "2024-01-01"},
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_response):
        await client.async_login()
    assert client._token == "abc123"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "result": "failed",
            "error_code": "login_failed_or_block",
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession.post", return_value=mock_response):
        with pytest.raises(VCVideoAuthError):
            await client.async_login()


@pytest.mark.asyncio
async def test_connection_error(client):
    with patch(
        "aiohttp.ClientSession.post",
        side_effect=aiohttp.ClientConnectorError(None, OSError()),
    ):
        with pytest.raises(VCVideoConnectionError):
            await client.async_login()
