"""Camera platform for VCVideo NVR."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    STATUS_ONLINE,
    STREAM_TYPE_MAIN,
    STREAM_TYPE_SUB,
)
from .coordinator import VCVideoCoordinator

_LOGGER = logging.getLogger(__name__)


def _channel_to_number(channel_id: str, fallback: int) -> int:
    """Extract a numeric channel number from IDs like 'IP_CH1', '01', 'CH3'."""
    if not channel_id:
        return fallback
    m = re.search(r"(\d+)", str(channel_id))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return fallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up VCVideo NVR cameras."""
    coordinator: VCVideoCoordinator = hass.data[DOMAIN][entry.entry_id]
    channels: list[dict] = coordinator.data or []

    entities: list[VCVideoCamera] = []
    for idx, channel in enumerate(channels):
        channel_id = channel.get("channel") or channel.get("channel_no") or f"CH{idx + 1}"
        name = (
            channel.get("channel_alias")
            or channel.get("channel_name")
            or channel.get("name")
            or f"Camera {channel_id}"
        )
        connect_status = (channel.get("connect_status") or "").lower()
        # Skip totally unconfigured channels
        if connect_status in ("not_configured", "notconfigured", "noconfig"):
            _LOGGER.debug("Skipping unconfigured channel %s", channel_id)
            continue

        entities.append(
            VCVideoCamera(
                coordinator=coordinator,
                entry=entry,
                channel_index=idx,
                channel_id=str(channel_id),
                channel_no=_channel_to_number(str(channel_id), idx + 1),
                channel_name=str(name).strip() or f"Camera {channel_id}",
            )
        )

    _LOGGER.info("Adding %d VCVideo NVR cameras", len(entities))
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
        channel_no: int,
        channel_name: str,
    ) -> None:
        """Initialize the camera entity."""
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._channel_index = channel_index
        self._channel_id = channel_id
        self._channel_no = channel_no
        self._channel_name = channel_name
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_camera_{channel_id}"
        self._attr_name = channel_name
        # Precompute RTSP URLs — the pattern is deterministic for this NVR.
        self._rtsp_url = coordinator.client.build_rtsp_url(
            channel_no, STREAM_TYPE_MAIN
        )
        self._rtsp_sub_url = coordinator.client.build_rtsp_url(
            channel_no, STREAM_TYPE_SUB
        )

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
            "channel_no": self._channel_no,
            "connect_status": ch.get("connect_status"),
            "ability": ch.get("ability"),
            "sub_stream_url": self._rtsp_sub_url,
        }

    async def stream_source(self) -> str | None:
        """Return RTSP stream URL (used by HA Streams/WebRTC)."""
        return self._rtsp_url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the camera."""
        return await self.coordinator.client.async_get_snapshot(self._channel_id)

