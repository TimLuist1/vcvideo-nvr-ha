"""DataUpdateCoordinator for VCVideo NVR."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    VCVideoAuthError,
    VCVideoConnectionError,
    VCVideoNVRClient,
    channel_to_number,
)
from .const import DOMAIN, HEARTBEAT_INTERVAL, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class VCVideoCoordinator(DataUpdateCoordinator[list[dict]]):
    """Manages polling and session for one VCVideo NVR."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VCVideoNVRClient,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.client = client
        self.device_info: dict = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._probe_task: asyncio.Task | None = None

    async def _async_update_data(self) -> list[dict]:
        """Fetch channel data from the NVR."""
        try:
            return await self.client.async_get_channel_info()
        except VCVideoAuthError:
            _LOGGER.debug("Session expired, re-authenticating")
        except VCVideoConnectionError as err:
            raise UpdateFailed(f"NVR unreachable: {err}") from err

        try:
            await self.client.async_login()
            return await self.client.async_get_channel_info()
        except VCVideoAuthError as err:
            # Credentials no longer work — ask the user to re-enter them.
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except VCVideoConnectionError as err:
            raise UpdateFailed(f"NVR unreachable: {err}") from err

    async def async_login_and_fetch(self) -> list[dict]:
        """Perform initial login and fetch all data."""
        await self.client.async_login()
        self.device_info = await self.client.async_get_device_info()
        channels = await self.client.async_get_channel_info()
        self._start_heartbeat()
        self._start_snapshot_probe(channels)
        return channels

    def _start_heartbeat(self) -> None:
        """Start background heartbeat task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = self.hass.async_create_background_task(
                self._heartbeat_loop(), "vcvideo_nvr_heartbeat"
            )

    def _start_snapshot_probe(self, channels: list[dict]) -> None:
        """Detect an HTTP snapshot endpoint in the background.

        Probing walks several candidate URLs and can take longer than the 10 s
        Home Assistant allows a camera to produce a still image, so it must
        never run inside a thumbnail request. Until it finishes, cameras grab
        their frames from RTSP.
        """
        if self.client.snapshot_probed or not channels:
            return
        if self._probe_task is not None and not self._probe_task.done():
            return

        first = channels[0]
        channel_id = str(first.get("channel") or first.get("channel_no") or "1")
        self._probe_task = self.hass.async_create_background_task(
            self._probe_snapshot(channel_id), "vcvideo_nvr_snapshot_probe"
        )

    async def _probe_snapshot(self, channel_id: str) -> None:
        """Run the snapshot endpoint probe, ignoring failures."""
        try:
            await self.client.async_probe_snapshot_endpoint(
                channel_id, channel_to_number(channel_id, 1)
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Snapshot endpoint probe failed: %s", err)

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
        await super().async_shutdown()
        for task in (self._heartbeat_task, self._probe_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._heartbeat_task = None
        self._probe_task = None
        await self.client.async_logout()
        await self.client.async_close()
