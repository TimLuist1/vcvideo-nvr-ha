"""Config flow for VCVideo NVR integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult

from .api import VCVideoAuthError, VCVideoConnectionError, VCVideoNVRClient
from .const import CONF_RTSP_PORT, DEFAULT_PORT, DEFAULT_RTSP_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_RTSP_PORT, default=DEFAULT_RTSP_PORT): int,
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class VCVideoNVRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VCVideo NVR."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            rtsp_port = user_input.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT)
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            client = VCVideoNVRClient(
                host=host,
                username=username,
                password=password,
                port=port,
                rtsp_port=rtsp_port,
            )

            try:
                await client.async_login()
                device_info = await client.async_get_device_info()
            except VCVideoAuthError:
                errors["base"] = "invalid_auth"
            except VCVideoConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during setup")
                errors["base"] = "unknown"
            else:
                title = device_info.get("device_name") or device_info.get("sn") or host
                await client.async_close()
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )
            await client.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration."""
        return await self.async_step_user(user_input)
