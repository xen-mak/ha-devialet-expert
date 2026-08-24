"""Config flow for Devialet Expert (non-Pro)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .api import DevialetClient, DevialetError, status_summary
from .const import (
    CONF_VOLUME_MAX_DB,
    CONF_VOLUME_MIN_DB,
    DEFAULT_VOLUME_MAX_DB,
    DEFAULT_VOLUME_MIN_DB,
    DOMAIN,
    HARDWARE_VOLUME_MAX_DB,
    HARDWARE_VOLUME_MIN_DB,
)


async def _async_validate_host(
    hass: HomeAssistant, host: str
) -> dict[str, object]:
    """Confirm that ``host`` is broadcasting valid Devialet status packets."""
    client = DevialetClient(host)
    return await hass.async_add_executor_job(client.get_status)


class DevialetExpertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup for a Devialet Expert non-Pro amplifier."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient discovery choices for this configuration flow."""
        self._discovered: dict[str, dict[str, object]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Offer an active UDP scan or manual host entry."""
        return self.async_show_menu(step_id="user", menu_options=["scan", "manual"])

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Listen briefly for Devialet status broadcasts and let the user choose one."""
        if user_input is None:
            statuses = await self.hass.async_add_executor_job(DevialetClient.scan)
            self._discovered = {
                str(status["ip"]): status for status in statuses if status.get("ip")
            }
            if not self._discovered:
                return self.async_abort(reason="no_devices_found")

            return self.async_show_form(
                step_id="scan",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST): vol.In(
                            {
                                host: status_summary(status)
                                for host, status in self._discovered.items()
                            }
                        )
                    }
                ),
            )

        return await self._async_create_entry_for_host(user_input[CONF_HOST])

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Validate an address supplied directly by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                return await self._async_create_entry_for_host(user_input[CONF_HOST])
            except DevialetError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_HOST): cv.string}),
            errors=errors,
        )

    async def _async_create_entry_for_host(self, host: str) -> FlowResult:
        """Validate a host, avoid exact duplicate entries, and create the entry."""
        host = host.strip()
        try:
            status = await _async_validate_host(self.hass, host)
        except DevialetError:
            raise

        self._async_abort_entries_match({CONF_HOST: host})
        return self.async_create_entry(
            title=status_summary(status),
            data={CONF_HOST: host},
            options={
                CONF_VOLUME_MIN_DB: DEFAULT_VOLUME_MIN_DB,
                CONF_VOLUME_MAX_DB: DEFAULT_VOLUME_MAX_DB,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow a changed DHCP address or hostname to be tested and saved."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                status = await _async_validate_host(self.hass, host)
            except DevialetError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): cv.string}
            ),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DevialetExpertOptionsFlow:
        """Return the runtime options form for a configured amplifier."""
        return DevialetExpertOptionsFlow(config_entry)


class DevialetExpertOptionsFlow(config_entries.OptionsFlow):
    """Handle configurable Home Assistant-side dB boundaries."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the entry whose display and write range will be changed."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure minimum and maximum user-facing volume in dB."""
        errors: dict[str, str] = {}
        if user_input is not None:
            volume_min = user_input[CONF_VOLUME_MIN_DB]
            volume_max = user_input[CONF_VOLUME_MAX_DB]
            if volume_min >= volume_max:
                errors["base"] = "invalid_volume_range"
            else:
                return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_VOLUME_MIN_DB,
                        default=options.get(
                            CONF_VOLUME_MIN_DB, DEFAULT_VOLUME_MIN_DB
                        ),
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(
                            min=HARDWARE_VOLUME_MIN_DB,
                            max=HARDWARE_VOLUME_MAX_DB,
                        ),
                    ),
                    vol.Required(
                        CONF_VOLUME_MAX_DB,
                        default=options.get(
                            CONF_VOLUME_MAX_DB, DEFAULT_VOLUME_MAX_DB
                        ),
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(
                            min=HARDWARE_VOLUME_MIN_DB,
                            max=HARDWARE_VOLUME_MAX_DB,
                        ),
                    ),
                }
            ),
            errors=errors,
        )
