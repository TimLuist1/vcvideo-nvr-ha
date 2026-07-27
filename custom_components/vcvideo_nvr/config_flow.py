"""Config flow for VCVideo NVR integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import VCVideoAuthError, VCVideoConnectionError, VCVideoNVRClient
from .const import (
    CONF_FFMPEG_ARGUMENTS,
    CONF_RTSP_PORT,
    CONF_SNAPSHOT_SOURCE,
    DEFAULT_FFMPEG_ARGUMENTS,
    DEFAULT_PORT,
    DEFAULT_RTSP_PORT,
    DEFAULT_SNAPSHOT_SOURCE,
    DOMAIN,
    SNAPSHOT_SOURCES,
)

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

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_SNAPSHOT_SOURCE, default=DEFAULT_SNAPSHOT_SOURCE
        ): SelectSelector(
            SelectSelectorConfig(
                options=SNAPSHOT_SOURCES,
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_SNAPSHOT_SOURCE,
            )
        ),
        vol.Optional(
            CONF_FFMPEG_ARGUMENTS, default=DEFAULT_FFMPEG_ARGUMENTS
        ): str,
    }
)


async def _async_validate_connection(data: dict[str, Any]) -> tuple[dict, str | None]:
    """Try to log in to the NVR.

    Returns the device info and an error key, exactly one of which is set.
    """
    client = VCVideoNVRClient(
        host=data[CONF_HOST],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        rtsp_port=data.get(CONF_RTSP_PORT, DEFAULT_RTSP_PORT),
    )
    try:
        await client.async_login()
        return await client.async_get_device_info(), None
    except VCVideoAuthError:
        return {}, "invalid_auth"
    except VCVideoConnectionError:
        return {}, "cannot_connect"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error connecting to the NVR")
        return {}, "unknown"
    finally:
        await client.async_close()


class VCVideoNVRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VCVideo NVR."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return VCVideoNVROptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            device_info, error = await _async_validate_connection(user_input)
            if error is None:
                return self.async_create_entry(
                    title=device_info.get("device_name")
                    or device_info.get("sn")
                    or host,
                    data=user_input,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_mismatch(reason="wrong_device")

            _device_info, error = await _async_validate_connection(user_input)
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle credentials that stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for new credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            _device_info, error = await _async_validate_connection(
                {**entry.data, **user_input}
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_REAUTH_DATA_SCHEMA,
                {CONF_USERNAME: entry.data.get(CONF_USERNAME)},
            ),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )


class VCVideoNVROptionsFlow(OptionsFlow):
    """Handle VCVideo NVR options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage snapshot options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
