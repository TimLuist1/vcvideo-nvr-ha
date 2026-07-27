"""Camera platform for VCVideo NVR."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import channel_to_number
from .const import (
    CONF_FFMPEG_ARGUMENTS,
    CONF_SNAPSHOT_SOURCE,
    DEFAULT_FFMPEG_ARGUMENTS,
    DEFAULT_SNAPSHOT_SOURCE,
    DOMAIN,
    MANUFACTURER,
    SNAPSHOT_CACHE_SECONDS,
    SNAPSHOT_SOURCE_AUTO,
    SNAPSHOT_SOURCE_HTTP,
    SNAPSHOT_SOURCE_NONE,
    SNAPSHOT_SOURCE_RTSP_MAIN,
    SNAPSHOT_SOURCE_RTSP_SUB,
    SNAPSHOT_TIMEOUT,
    STATUS_DOWN,
    STATUS_UNUSABLE,
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

    entities: list[VCVideoCamera] = []
    for idx, channel in enumerate(channels):
        channel_id = channel.get("channel") or channel.get("channel_no") or f"CH{idx + 1}"
        name = (
            channel.get("channel_alias")
            or channel.get("channel_name")
            or channel.get("name")
            or f"Camera {channel_id}"
        )
        connect_status = str(channel.get("connect_status") or "").lower()
        # Skip totally unconfigured channels
        if connect_status in STATUS_UNUSABLE:
            _LOGGER.debug("Skipping unconfigured channel %s", channel_id)
            continue

        entities.append(
            VCVideoCamera(
                coordinator=coordinator,
                entry=entry,
                channel_index=idx,
                channel_id=str(channel_id),
                channel_no=channel_to_number(str(channel_id), idx + 1),
                channel_name=str(name).strip() or f"Camera {channel_id}",
            )
        )

    _LOGGER.debug("Adding %d VCVideo NVR cameras", len(entities))
    async_add_entities(entities)


class VCVideoCamera(CoordinatorEntity[VCVideoCoordinator], Camera):
    """Represents a single camera channel from a VCVideo NVR."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_is_streaming = True

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
        options = entry.options
        self._snapshot_source: str = options.get(
            CONF_SNAPSHOT_SOURCE, DEFAULT_SNAPSHOT_SOURCE
        )
        self._ffmpeg_arguments: str = options.get(
            CONF_FFMPEG_ARGUMENTS, DEFAULT_FFMPEG_ARGUMENTS
        )
        self._image_lock = asyncio.Lock()
        self._last_image: bytes | None = None
        self._last_image_at: float = 0.0
        self._image_error_logged = False

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
    def _connect_status(self) -> str:
        """Return the channel's connect status, lowercased."""
        return str(self._channel_data.get("connect_status") or "").lower()

    @property
    def is_on(self) -> bool:
        """Return True if the camera is online."""
        status = self._connect_status
        return status not in STATUS_DOWN and status not in STATUS_UNUSABLE

    @property
    def available(self) -> bool:
        """Return True if the NVR responds and the channel is connected.

        Unknown connect states are treated as available: firmwares report a
        range of values here and the stream usually works regardless.
        """
        if not self.coordinator.last_update_success:
            return False
        return self._connect_status not in STATUS_DOWN

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes.

        The RTSP URLs are deliberately omitted — they embed the NVR password
        and would end up in the state machine, the recorder and any log.
        """
        ch = self._channel_data
        return {
            "channel_id": self._channel_id,
            "channel_no": self._channel_no,
            "connect_status": ch.get("connect_status"),
            "ability": ch.get("ability"),
            "snapshot_source": self._active_snapshot_source,
        }

    @property
    def _active_snapshot_source(self) -> str:
        """Return the snapshot source actually in use."""
        if self._snapshot_source != SNAPSHOT_SOURCE_AUTO:
            return self._snapshot_source
        if self.coordinator.client.snapshot_endpoint:
            return SNAPSHOT_SOURCE_HTTP
        return SNAPSHOT_SOURCE_RTSP_SUB

    async def stream_source(self) -> str | None:
        """Return RTSP stream URL (used by HA Streams/WebRTC)."""
        return self._rtsp_url

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image for the camera thumbnail.

        Most firmwares of this NVR expose no HTTP still-image CGI, which is why
        thumbnails used to stay blank while the live stream played fine. The
        image is therefore taken from the RTSP stream with ffmpeg whenever the
        NVR cannot serve one over HTTP.
        """
        if self._snapshot_source == SNAPSHOT_SOURCE_NONE:
            return None

        # The cache is not keyed on the requested size: Home Assistant rescales
        # JPEGs itself, so one frame per interval serves every dashboard card.
        now = time.monotonic()
        if self._last_image and now - self._last_image_at < SNAPSHOT_CACHE_SECONDS:
            return self._last_image

        async with self._image_lock:
            # A parallel request may have refreshed the cache while we waited.
            now = time.monotonic()
            if self._last_image and now - self._last_image_at < SNAPSHOT_CACHE_SECONDS:
                return self._last_image

            image = await self._async_fetch_image(width, height)

        if image:
            self._last_image = image
            self._last_image_at = time.monotonic()
            self._image_error_logged = False
            return image

        if not self._image_error_logged:
            self._image_error_logged = True
            _LOGGER.warning(
                "Could not get a still image for %s (channel %s). The live "
                "stream is unaffected; check that ffmpeg works and that the "
                "RTSP stream is reachable",
                self._channel_name,
                self._channel_id,
            )
        # Serve the last known frame rather than a broken thumbnail.
        return self._last_image

    async def _async_fetch_image(
        self, width: int | None, height: int | None
    ) -> bytes | None:
        """Fetch a still image from the configured source."""
        source = self._snapshot_source

        if source in (SNAPSHOT_SOURCE_AUTO, SNAPSHOT_SOURCE_HTTP):
            # probe=False: endpoint detection runs in the background at setup,
            # so a still-running probe never eats into the 10 s image timeout.
            image = await self.coordinator.client.async_get_snapshot(
                self._channel_id,
                self._channel_no,
                probe=source == SNAPSHOT_SOURCE_HTTP,
            )
            if image or source == SNAPSHOT_SOURCE_HTTP:
                return image

        stream_url = (
            self._rtsp_url
            if source == SNAPSHOT_SOURCE_RTSP_MAIN
            else self._rtsp_sub_url
        )
        return await self._async_ffmpeg_image(stream_url, width, height)

    async def _async_ffmpeg_image(
        self, stream_url: str, width: int | None, height: int | None
    ) -> bytes | None:
        """Grab a single frame from an RTSP stream with ffmpeg."""
        input_source = stream_url
        if self._ffmpeg_arguments:
            # haffmpeg splits a multi-token input source itself, which is how
            # input options such as -rtsp_transport get in front of -i.
            input_source = f"{self._ffmpeg_arguments} -i {stream_url}"
        try:
            async with asyncio.timeout(SNAPSHOT_TIMEOUT):
                return await async_get_image(
                    self.hass, input_source, width=width, height=height
                )
        except TimeoutError:
            _LOGGER.debug(
                "Timed out grabbing a frame for channel %s after %s s",
                self._channel_id,
                SNAPSHOT_TIMEOUT,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "ffmpeg snapshot failed for channel %s: %s", self._channel_id, err
            )
        return None
