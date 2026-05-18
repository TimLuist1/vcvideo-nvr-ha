"""Camera platform for VCVideo NVR."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_RTSP_PORT,
    DOMAIN,
    MANUFACTURER,
    CONF_RTSP_PORT,
    STATUS_ONLINE,
    STREAM_TYPE_MAIN,
    STREAM_TYPE_SUB,
)
from .coordinator import VCVideoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VCVideo NVR cameras."""
    coordinator: VCVideoCoordinator = hass.data[DOMAIN][entry.entry_id]
    channels: list[dict] = coordinator.data or []

    entities = []
    for idx, channel in enumerate(channels):
        channel_id = channel.get("channel") or channel.get("channel_no") or str(idx + 1)
        name = (
            channel.get("channel_name")
            or channel.get("name")
            or f"Camera {channel_id}"
        )
        connect_status = (channel.get("connect_status") or "").lower()
        # Skip totally unconfigured channels
        if connect_status in ("not_configured", "notconfigured"):
            continue

        entities.append(
            VCVideoCamera(
                coordinator=coordinator,
                entry=entry,
                channel_index=idx,
                channel_id=str(channel_id),
                channel_name=name,
            )
        )
        _LOGGER.debug("Adding camera entity: %s (channel %s)", name, channel_id)

    async_add_entities(entities)


class VCVideoCamera(CoordinatorEntity[VCVideoCoordinator], Camera):
    """Represents a single camera channel from a VCVideo NVR."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(
        self,
        coordinator: VCVideoCoordinator,
        entry: ConfigEntry,
        channel_index: int,
        channel_id: str,
        channel_name: str,
    ) -> None:
        """Initialize the camera entity."""
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._channel_index = channel_index
        self._channel_id = channel_id
        self._channel_name = channel_name
        self._entry = entry
        self._rtsp_url: str | None = None
        self._rtsp_sub_url: str | None = None
        self._attr_unique_id = f"{entry.entry_id}_camera_{channel_id}"
        self._attr_name = channel_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the NVR."""
        dev = self.coordinator.device_info
        host = self._entry.data[CONF_HOST]
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=dev.get("device_name") or dev.get("sn") or f"VCVideo NVR ({host})",
            manufacturer=MANUFACTURER,
            model=dev.get("device_type") or dev.get("model") or "NVR",
            sw_version=dev.get("soft_version") or dev.get("firmware_version"),
            configuration_url=f"http://{host}",
        )

    @property
    def _channel_data(self) -> dict:
        """Return current channel data from coordinator."""
        channels: list[dict] = self.coordinator.data or []
        if self._channel_index < len(channels):
            return channels[self._channel_index]
        return {}

    @property
    def is_on(self) -> bool:
        """Return True if the camera is online."""
        status = (self._channel_data.get("connect_status") or "").lower()
        return status in (STATUS_ONLINE, "online", "")

    @property
    def available(self) -> bool:
        """Return True if coordinator has data."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        ch = self._channel_data
        return {
            "channel_id": self._channel_id,
            "connect_status": ch.get("connect_status"),
            "channel_type": ch.get("channel_type") or ch.get("type"),
            "ability": ch.get("ability"),
        }

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to HA — resolve stream URLs."""
        await super().async_added_to_hass()
        await self._async_resolve_stream_url()

    async def _async_resolve_stream_url(self) -> None:
        """Try to get stream URL via API, fall back to constructed RTSP URL."""
        client = self.coordinator.client
        # Try API first
        url = await client.async_get_stream_url(self._channel_id, STREAM_TYPE_MAIN)
        if url:
            self._rtsp_url = url
        else:
            # Build standard RTSP URL
            try:
                ch_int = int(self._channel_id.lstrip("0") or "0")
            except ValueError:
                ch_int = self._channel_index + 1
            self._rtsp_url = client.build_rtsp_url(ch_int, STREAM_TYPE_MAIN)

        # Sub-stream
        sub_url = await client.async_get_stream_url(self._channel_id, STREAM_TYPE_SUB)
        if sub_url:
            self._rtsp_sub_url = sub_url
        else:
            try:
                ch_int = int(self._channel_id.lstrip("0") or "0")
            except ValueError:
                ch_int = self._channel_index + 1
            self._rtsp_sub_url = client.build_rtsp_url(ch_int, STREAM_TYPE_SUB)

        _LOGGER.debug(
            "Camera %s main stream: %s",
            self._channel_name,
            self._rtsp_url,
        )

    async def stream_source(self) -> str | None:
        """Return RTSP stream URL (used by HA Streams/WebRTC)."""
        if not self._rtsp_url:
            await self._async_resolve_stream_url()
        return self._rtsp_url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the camera."""
        image = await self.coordinator.client.async_get_snapshot(self._channel_id)
        return image

    def _handle_coordinator_update(self) -> None:
        """Handle coordinator data updates."""
        super()._handle_coordinator_update()
