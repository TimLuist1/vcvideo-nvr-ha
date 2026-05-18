"""DataUpdateCoordinator for VCVideo NVR."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VCVideoAuthError, VCVideoConnectionError, VCVideoNVRClient
from .const import DOMAIN, HEARTBEAT_INTERVAL, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class VCVideoCoordinator(DataUpdateCoordinator):
    """Manages polling and session for one VCVideo NVR."""

    def __init__(self, hass: HomeAssistant, client: VCVideoNVRClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = client
        self.device_info: dict = {}
        self._heartbeat_task: asyncio.Task | None = None

    async def _async_update_data(self) -> list[dict]:
        """Fetch channel data from the NVR."""
        try:
            channels = await self.client.async_get_channel_info()
            return channels
        except VCVideoAuthError:
            _LOGGER.warning("Session expired, re-authenticating")
            try:
                await self.client.async_login()
                return await self.client.async_get_channel_info()
            except (VCVideoAuthError, VCVideoConnectionError) as err:
                raise UpdateFailed(f"Authentication failed: {err}") from err
        except VCVideoConnectionError as err:
            raise UpdateFailed(f"NVR unreachable: {err}") from err

    async def async_login_and_fetch(self) -> list[dict]:
        """Perform initial login and fetch all data."""
        await self.client.async_login()
        self.device_info = await self.client.async_get_device_info()
        channels = await self.client.async_get_channel_info()
        self._start_heartbeat()
        return channels

    def _start_heartbeat(self) -> None:
        """Start background heartbeat task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = self.hass.async_create_background_task(
                self._heartbeat_loop(), "vcvideo_nvr_heartbeat"
            )

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to keep the NVR session alive."""
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                alive = await self.client.async_heartbeat()
                if not alive:
                    _LOGGER.debug("Heartbeat failed, re-authenticating")
                    await self.client.async_login()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Heartbeat error: %s", err)

    async def async_shutdown(self) -> None:
        """Shut down the coordinator and close the client."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.client.async_logout()
        await self.client.async_close()
