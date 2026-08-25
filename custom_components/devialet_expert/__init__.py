"""The Devialet Expert (non-Pro) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import DevialetClient, DevialetError
from .const import PLATFORMS
from .coordinator import DevialetDataUpdateCoordinator


type DevialetConfigEntry = ConfigEntry[DevialetDataUpdateCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: DevialetConfigEntry
) -> bool:
    """Set up Devialet Expert from a config entry."""
    client = DevialetClient(entry.data[CONF_HOST])
    coordinator = DevialetDataUpdateCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    try:
        await coordinator.async_start_listening()
    except DevialetError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.async_on_unload(coordinator.async_stop_listening)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: DevialetConfigEntry
) -> bool:
    """Unload a Devialet Expert config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: DevialetConfigEntry
) -> None:
    """Reload after reconfiguration of a host address."""
    await hass.config_entries.async_reload(entry.entry_id)
