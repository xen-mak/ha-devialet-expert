"""Coordinator for Devialet Expert non-Pro status updates."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import DevialetClient, DevialetError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class DevialetDataUpdateCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Fetch and cache the latest amplifier status broadcast."""

    def __init__(self, hass: HomeAssistant, client: DevialetClient) -> None:
        """Initialize the coordinator for one configured amplifier."""
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, object]:
        """Receive a status packet without blocking Home Assistant's event loop."""
        try:
            return await self.hass.async_add_executor_job(self.client.get_status)
        except DevialetError as err:
            raise UpdateFailed(str(err)) from err

    async def async_execute(self, method_name: str, *args: Any) -> None:
        """Run a named synchronous protocol command and promptly refresh state."""
        method = getattr(self.client, method_name)
        try:
            await self.hass.async_add_executor_job(method, *args)
        except DevialetError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()
