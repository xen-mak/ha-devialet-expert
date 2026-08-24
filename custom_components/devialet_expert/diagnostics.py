"""Diagnostics support for Devialet Expert (non-Pro)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import CONF_HOST
from .coordinator import DevialetDataUpdateCoordinator


def _redact_host(host: str) -> str:
    """Keep only a small non-sensitive hint of the configured network location."""
    if "." in host:
        parts = host.split(".")
        return ".".join(["***"] * max(len(parts) - 1, 1) + [parts[-1]])
    return "***"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry[DevialetDataUpdateCoordinator],
) -> dict[str, Any]:
    """Return a sanitized coordinator snapshot for support requests."""
    status = dict(entry.runtime_data.data or {})
    for key in ("ip",):
        if key in status:
            status[key] = _redact_host(str(status[key]))

    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)},
            {CONF_HOST},
        ),
        "status": status,
        "last_update_success": entry.runtime_data.last_update_success,
        "last_exception": str(entry.runtime_data.last_exception)
        if entry.runtime_data.last_exception
        else None,
    }
