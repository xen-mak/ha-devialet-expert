"""Media player platform for Devialet Expert non-Pro amplifiers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_VOLUME_MAX_DB,
    CONF_VOLUME_MIN_DB,
    DEFAULT_VOLUME_MAX_DB,
    DEFAULT_VOLUME_MIN_DB,
    DOMAIN,
    HARDWARE_VOLUME_MAX_DB,
    HARDWARE_VOLUME_MIN_DB,
    MANUFACTURER,
    MODEL,
)
from .coordinator import DevialetDataUpdateCoordinator


type DevialetConfigEntry = ConfigEntry[DevialetDataUpdateCoordinator]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DevialetConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Devialet Expert media player from a config entry."""
    async_add_entities([DevialetExpertMediaPlayer(entry.runtime_data, entry)])


class DevialetExpertMediaPlayer(
    CoordinatorEntity[DevialetDataUpdateCoordinator], MediaPlayerEntity
):
    """Represent a Devialet Expert non-Pro amplifier as a media player."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_should_poll = False
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(
        self, coordinator: DevialetDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the entity using the immutable config entry id."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = entry.entry_id

    @property
    def _status(self) -> Mapping[str, object]:
        """Return the most recently coordinator-cached amplifier state."""
        return self.coordinator.data or {}

    @property
    def available(self) -> bool:
        """Report available whenever the listener is running.

        A silent amplifier is reported through the state as idle rather than by
        making the entity unavailable, which would hide its last known values.
        """
        return super().available

    @property
    def device_info(self) -> DeviceInfo:
        """Return device metadata without inventing a non-existent hardware serial."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=str(self._status.get("dev_name") or self._entry.title),
        )

    @property
    def state(self) -> MediaPlayerState:
        """Map the physical power state to Home Assistant's media player state."""
        if self.coordinator.silent:
            return MediaPlayerState.IDLE
        return (
            MediaPlayerState.ON
            if bool(self._status.get("power"))
            else MediaPlayerState.OFF
        )

    @property
    def is_volume_muted(self) -> bool | None:
        """Return the physical mute state from the latest status broadcast."""
        value = self._status.get("muted")
        return bool(value) if value is not None else None

    @property
    def _volume_min_db(self) -> float:
        """Return the configured lower edge for the Home Assistant volume slider."""
        return float(
            self._entry.options.get(CONF_VOLUME_MIN_DB, DEFAULT_VOLUME_MIN_DB)
        )

    @property
    def _volume_max_db(self) -> float:
        """Return the configured upper edge for the Home Assistant volume slider."""
        return float(
            self._entry.options.get(CONF_VOLUME_MAX_DB, DEFAULT_VOLUME_MAX_DB)
        )

    @property
    def volume_level(self) -> float | None:
        """Return dB volume normalized to the user's configured Home Assistant range."""
        volume_db = self._status.get("volume_db")
        if not isinstance(volume_db, (int, float)):
            return None
        bounded_db = min(max(float(volume_db), self._volume_min_db), self._volume_max_db)
        return (bounded_db - self._volume_min_db) / (
            self._volume_max_db - self._volume_min_db
        )

    @property
    def volume_step(self) -> float:
        """Use the amplifier's 0.5 dB physical resolution as UI volume step."""
        return 0.5 / (self._volume_max_db - self._volume_min_db)

    @property
    def _source_map(self) -> dict[str, int]:
        """Map human-readable, unique source labels to protocol channel indexes."""
        mapping: dict[str, int] = {}
        channels = self._status.get("ch_list")
        if not isinstance(channels, Mapping):
            return mapping
        for channel, display_name in channels.items():
            label = str(display_name) or f"Channel {channel}"
            if label in mapping:
                label = f"{label} (channel {channel})"
            mapping[label] = int(channel)
        return mapping

    @property
    def source_list(self) -> list[str]:
        """Return all enabled amplifier inputs in protocol-channel order."""
        return list(self._source_map)

    @property
    def source(self) -> str | None:
        """Return the source label associated with the active protocol channel."""
        channel = self._status.get("channel")
        if not isinstance(channel, int):
            return None
        for source, source_channel in self._source_map.items():
            if source_channel == channel:
                return source
        return f"Channel {channel}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the decoded status fields that are useful in automations.

        The active input and the list of inputs are already carried by the
        standard ``source`` and ``source_list`` properties, so the raw protocol
        channel numbering is not repeated here.
        """
        return {
            "device_name": self._status.get("dev_name"),
            "ip_address": self._status.get("ip"),
            "volume_db": self._status.get("volume_db"),
            "raw_volume": self._status.get("raw_volume"),
            "connected": not self.coordinator.silent,
            "configured_host": self._entry.data[CONF_HOST],
            "volume_min_db": self._volume_min_db,
            "volume_max_db": self._volume_max_db,
        }

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume from a normalized Home Assistant slider value."""
        if not 0.0 <= volume <= 1.0:
            raise HomeAssistantError("Volume level must be between 0.0 and 1.0")
        target_db = self._volume_min_db + volume * (
            self._volume_max_db - self._volume_min_db
        )
        target_db = min(max(target_db, HARDWARE_VOLUME_MIN_DB), HARDWARE_VOLUME_MAX_DB)
        await self.coordinator.async_execute("set_volume", target_db)

    async def async_mute_volume(self, mute: bool) -> None:
        """Set mute or unmute explicitly, without toggle-state races."""
        await self.coordinator.async_execute("set_muted", mute)

    async def async_turn_on(self) -> None:
        """Power on the physical amplifier."""
        await self.coordinator.async_execute("set_power", True)

    async def async_turn_off(self) -> None:
        """Put the physical amplifier into standby."""
        await self.coordinator.async_execute("set_power", False)

    async def async_select_source(self, source: str) -> None:
        """Switch to an enabled source named in ``source_list``."""
        try:
            channel = self._source_map[source]
        except KeyError as err:
            raise HomeAssistantError(f"Unknown Devialet source: {source}") from err
        await self.coordinator.async_execute("set_source", channel)
