"""Coordinator for Devialet Expert non-Pro status updates."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    DevialetClient,
    DevialetConnectionError,
    DevialetError,
    DevialetProtocolError,
    decode_status_packet,
    open_status_socket,
    resolve_addresses,
)
from .const import DOMAIN, IDLE_AFTER_SECONDS

_LOGGER = logging.getLogger(__name__)


class DevialetDataUpdateCoordinator(DataUpdateCoordinator[dict[str, object]]):
    """Hold the latest amplifier status, refreshed by broadcast rather than polling.

    The amplifier broadcasts its full state at roughly 10 Hz, so a persistent
    listener reflects a physical volume knob or handset almost immediately.
    ``update_interval`` stays ``None``: there is nothing to poll for.
    """

    def __init__(self, hass: HomeAssistant, client: DevialetClient) -> None:
        """Initialize the coordinator for one configured amplifier."""
        super().__init__(hass, logger=_LOGGER, name=DOMAIN, update_interval=None)
        self.client = client
        self._transport: asyncio.DatagramTransport | None = None
        self._expected_addresses: set[str] = set()
        self._cancel_watchdog: CALLBACK_TYPE | None = None
        self.silent = False

    async def _async_update_data(self) -> dict[str, object]:
        """Fetch one status packet, used only for the setup-time connectivity check."""
        try:
            return await self.hass.async_add_executor_job(self.client.get_status)
        except DevialetError as err:
            raise UpdateFailed(str(err)) from err

    async def async_start_listening(self) -> None:
        """Begin receiving broadcast status packets from the amplifier."""
        self._expected_addresses = await self.hass.async_add_executor_job(
            resolve_addresses, self.client.host
        )
        sock = await self.hass.async_add_executor_job(open_status_socket)
        try:
            transport, _ = await self.hass.loop.create_datagram_endpoint(
                lambda: _StatusListener(self), sock=sock
            )
        except OSError as err:
            sock.close()
            raise DevialetConnectionError(
                f"Unable to listen for Devialet status broadcasts: {err}"
            ) from err

        self._transport = transport
        self._schedule_watchdog()

    @callback
    def async_stop_listening(self) -> None:
        """Release the listening socket and the availability watchdog."""
        if self._cancel_watchdog is not None:
            self._cancel_watchdog()
            self._cancel_watchdog = None
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    @callback
    def async_handle_datagram(self, data: bytes, address: str) -> None:
        """Decode one broadcast and publish it when it carries something new."""
        if address not in self._expected_addresses:
            return
        try:
            status = decode_status_packet(data, address)
        except DevialetProtocolError as err:
            _LOGGER.debug("Undecodable datagram from %s: %s", address, err)
            return

        self._schedule_watchdog()
        was_silent = self.silent
        self.silent = False

        # At ~10 Hz most packets repeat the previous state verbatim. Publishing
        # only genuine changes keeps the entity responsive without waking every
        # state listener ten times a second. The first packet after a silence
        # must always publish, so the entity stops reporting idle.
        if not was_silent and self.last_update_success and status == self.data:
            return
        self.async_set_updated_data(status)

    @callback
    def _schedule_watchdog(self) -> None:
        """Restart the countdown after which the amplifier is reported idle."""
        if self._cancel_watchdog is not None:
            self._cancel_watchdog()
        self._cancel_watchdog = async_call_later(
            self.hass, IDLE_AFTER_SECONDS, self._async_handle_silence
        )

    @callback
    def _async_handle_silence(self, _now: Any) -> None:
        """Report idle after a spell with no status broadcast.

        The coordinator is deliberately not put into an error state. Nothing has
        failed: the listener is healthy and the amplifier has simply stopped
        announcing itself, so the entity stays available and reports idle.
        """
        self._cancel_watchdog = None
        if self.silent:
            return
        _LOGGER.debug(
            "No status broadcast from %s in %.0f seconds; reporting idle",
            self.client.host,
            IDLE_AFTER_SECONDS,
        )
        self.silent = True
        self.async_update_listeners()

    async def async_execute(self, method_name: str, *args: Any) -> None:
        """Run a named synchronous protocol command.

        No refresh is requested afterwards: the amplifier broadcasts the result
        of the command within about a tenth of a second.
        """
        method = getattr(self.client, method_name)
        try:
            await self.hass.async_add_executor_job(method, *args)
        except DevialetError as err:
            raise UpdateFailed(str(err)) from err


class _StatusListener(asyncio.DatagramProtocol):
    """Forward status broadcasts to the coordinator on the event loop."""

    def __init__(self, coordinator: DevialetDataUpdateCoordinator) -> None:
        """Bind this protocol to the coordinator it feeds."""
        self._coordinator = coordinator

    def datagram_received(self, data: bytes, addr: tuple[str | Any, ...]) -> None:
        """Hand one received datagram to the coordinator."""
        self._coordinator.async_handle_datagram(data, str(addr[0]))

    def error_received(self, exc: Exception) -> None:
        """Log a datagram-level error without tearing the listener down."""
        _LOGGER.debug("Devialet status socket error: %s", exc)
