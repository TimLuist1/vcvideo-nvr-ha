"""VCVideo NVR integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import VCVideoAuthError, VCVideoConnectionError, VCVideoNVRClient
from .const import CONF_RTSP_PORT, DEFAULT_PORT, DEFAULT_RTSP_PORT, DOMAIN
from .coordinator import VCVideoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VCVideo NVR from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    rtsp_port = entry.data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]

    # NOTE: we deliberately do NOT use HA's shared aiohttp ClientSession because
    # we need to attach DigestAuthMiddleware at session level for the NVR.
    client = VCVideoNVRClient(
        host=host,
        username=username,
        password=password,
        port=port,
        rtsp_port=rtsp_port,
    )

    coordinator = VCVideoCoordinator(hass, client, entry)

    try:
        channels = await coordinator.async_login_and_fetch()
    except VCVideoAuthError as err:
        await client.async_close()
        raise ConfigEntryAuthFailed(f"Invalid credentials for {host}: {err}") from err
    except VCVideoConnectionError as err:
        await client.async_close()
        raise ConfigEntryNotReady(f"Cannot connect to NVR at {host}: {err}") from err
    except Exception as err:
        await client.async_close()
        _LOGGER.exception("Unexpected error setting up VCVideo NVR at %s", host)
        raise ConfigEntryNotReady(f"Unexpected error: {err}") from err

    # Seed coordinator.data so platforms see channels immediately.
    coordinator.async_set_updated_data(channels)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: VCVideoCoordinator | None = hass.data.get(DOMAIN, {}).pop(
            entry.entry_id, None
        )
        if coordinator is not None:
            await coordinator.async_shutdown()
        if not hass.data.get(DOMAIN):
            hass.data.pop(DOMAIN, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
