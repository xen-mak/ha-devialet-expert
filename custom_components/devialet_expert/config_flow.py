"""Config flow for Devialet Expert (non-Pro)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import DevialetClient, DevialetError, status_summary
from .const import (
    CONF_DEVICE,
    CONF_VOLUME_MAX_DB,
    CONF_VOLUME_MIN_DB,
    DEFAULT_VOLUME_MAX_DB,
    DEFAULT_VOLUME_MIN_DB,
    DOMAIN,
    HARDWARE_VOLUME_MAX_DB,
    HARDWARE_VOLUME_MIN_DB,
    MANUAL_HOST,
    VOLUME_STEP_DB,
)

_HOST_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
_DB_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=HARDWARE_VOLUME_MIN_DB,
        max=HARDWARE_VOLUME_MAX_DB,
        step=VOLUME_STEP_DB,
        mode=NumberSelectorMode.BOX,
        unit_of_measurement="dB",
    )
)


async def _async_validate_host(
    hass: HomeAssistant, host: str
) -> dict[str, object]:
    """Confirm that ``host`` is broadcasting valid Devialet status packets."""
    client = DevialetClient(host)
    return await hass.async_add_executor_job(client.get_status)


def _volume_fields(
    volume_min: float, volume_max: float
) -> dict[Any, Any]:
    """Return the dB limit fields shared by the setup and reconfigure forms."""
    return {
        vol.Required(CONF_VOLUME_MIN_DB, default=volume_min): _DB_SELECTOR,
        vol.Required(CONF_VOLUME_MAX_DB, default=volume_max): _DB_SELECTOR,
    }


class DevialetExpertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle setup for a Devialet Expert non-Pro amplifier."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize transient discovery choices for this configuration flow."""
        self._discovered: dict[str, dict[str, object]] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Discover amplifiers and collect every setting in a single form."""
        if self._discovered is None:
            statuses = await self.hass.async_add_executor_job(DevialetClient.scan)
            self._discovered = {
                str(status["ip"]): status for status in statuses if status.get("ip")
            }

        errors: dict[str, str] = {}
        if user_input is not None:
            selected = user_input.get(CONF_DEVICE, MANUAL_HOST)
            host = str(user_input.get(CONF_HOST) or "").strip()
            if selected != MANUAL_HOST:
                host = str(selected)
            volume_min = float(user_input[CONF_VOLUME_MIN_DB])
            volume_max = float(user_input[CONF_VOLUME_MAX_DB])

            if not host:
                errors[CONF_HOST] = "host_required"
            elif volume_min >= volume_max:
                errors[CONF_VOLUME_MIN_DB] = "invalid_volume_range"
            else:
                try:
                    status = await _async_validate_host(self.hass, host)
                except DevialetError:
                    errors["base"] = "cannot_connect"
                else:
                    self._async_abort_entries_match({CONF_HOST: host})
                    return self.async_create_entry(
                        title=status_summary(status),
                        data={CONF_HOST: host},
                        options={
                            CONF_VOLUME_MIN_DB: volume_min,
                            CONF_VOLUME_MAX_DB: volume_max,
                        },
                    )

        schema = self._build_schema()
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={"found": str(len(self._discovered))},
        )

    def _build_schema(self) -> vol.Schema:
        """Build the single setup form from the current discovery result."""
        discovered = self._discovered or {}
        fields: dict[Any, Any] = {}

        if discovered:
            options = [
                SelectOptionDict(value=host, label=status_summary(status))
                for host, status in discovered.items()
            ]
            options.append(
                SelectOptionDict(
                    value=MANUAL_HOST, label="Enter an address manually below"
                )
            )
            fields[vol.Required(CONF_DEVICE, default=next(iter(discovered)))] = (
                SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN
                    )
                )
            )
            fields[vol.Optional(CONF_HOST, default="")] = _HOST_SELECTOR
        else:
            fields[vol.Required(CONF_HOST)] = _HOST_SELECTOR

        fields.update(_volume_fields(DEFAULT_VOLUME_MIN_DB, DEFAULT_VOLUME_MAX_DB))
        return vol.Schema(fields)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow the address and the dB limits to be tested and saved together."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            volume_min = float(user_input[CONF_VOLUME_MIN_DB])
            volume_max = float(user_input[CONF_VOLUME_MAX_DB])
            if volume_min >= volume_max:
                errors[CONF_VOLUME_MIN_DB] = "invalid_volume_range"
            else:
                try:
                    await _async_validate_host(self.hass, host)
                except DevialetError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={CONF_HOST: host},
                        options={
                            CONF_VOLUME_MIN_DB: volume_min,
                            CONF_VOLUME_MAX_DB: volume_max,
                        },
                    )

        options = entry.options
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): _HOST_SELECTOR,
                **_volume_fields(
                    options.get(CONF_VOLUME_MIN_DB, DEFAULT_VOLUME_MIN_DB),
                    options.get(CONF_VOLUME_MAX_DB, DEFAULT_VOLUME_MAX_DB),
                ),
            }
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)

        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DevialetExpertOptionsFlow:
        """Return the runtime options form for a configured amplifier."""
        return DevialetExpertOptionsFlow()


class DevialetExpertOptionsFlow(config_entries.OptionsFlow):
    """Handle configurable Home Assistant-side dB boundaries."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure minimum and maximum user-facing volume in dB."""
        errors: dict[str, str] = {}
        if user_input is not None:
            volume_min = float(user_input[CONF_VOLUME_MIN_DB])
            volume_max = float(user_input[CONF_VOLUME_MAX_DB])
            if volume_min >= volume_max:
                errors[CONF_VOLUME_MIN_DB] = "invalid_volume_range"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_VOLUME_MIN_DB: volume_min,
                        CONF_VOLUME_MAX_DB: volume_max,
                    },
                )

        options = self.config_entry.options
        schema = vol.Schema(
            _volume_fields(
                options.get(CONF_VOLUME_MIN_DB, DEFAULT_VOLUME_MIN_DB),
                options.get(CONF_VOLUME_MAX_DB, DEFAULT_VOLUME_MAX_DB),
            )
        )
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)

        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
