"""Constants for the Devialet Expert (non-Pro) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "devialet_expert"
PLATFORMS: Final = ["media_player"]

CONF_HOST: Final = "host"
CONF_VOLUME_MIN_DB: Final = "volume_min_db"
CONF_VOLUME_MAX_DB: Final = "volume_max_db"

DEFAULT_VOLUME_MIN_DB: Final = -97.5
DEFAULT_VOLUME_MAX_DB: Final = -10.0
HARDWARE_VOLUME_MIN_DB: Final = -97.5
HARDWARE_VOLUME_MAX_DB: Final = -10.0
VOLUME_STEP_DB: Final = 0.5

UDP_PORT_STATUS: Final = 45454
UDP_PORT_COMMAND: Final = 45455
STATUS_PACKET_SIZE: Final = 512
COMMAND_PACKET_SIZE: Final = 142
STATUS_TIMEOUT_SECONDS: Final = 2.0
DISCOVERY_TIMEOUT_SECONDS: Final = 5.0
SCAN_MAX_DEVICES: Final = 20
UPDATE_INTERVAL_SECONDS: Final = 2

MANUFACTURER: Final = "Devialet"
MODEL: Final = "Expert (non-Pro)"
ATTRIBUTION: Final = "Data provided by the local Devialet Expert UDP protocol"

SERVICE_SET_VOLUME_DB: Final = "set_volume_db"
