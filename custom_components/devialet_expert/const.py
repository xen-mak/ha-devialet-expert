"""Constants for the Devialet Expert (non-Pro) integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "devialet_expert"
PLATFORMS: Final = ["media_player"]

CONF_HOST: Final = "host"
CONF_DEVICE: Final = "device"
CONF_VOLUME_MIN_DB: Final = "volume_min_db"
CONF_VOLUME_MAX_DB: Final = "volume_max_db"

# Sentinel option that turns the discovered-device picker into manual entry.
MANUAL_HOST: Final = "__manual__"

# The status byte maps to dB as (raw - 195) / 2, so raw 0 is -97.5 dB. That is a
# hard floor of the wire format, not a policy choice: no smaller value exists.
# The ceiling is a safety policy. Upstream DeviMote refuses to send above -10 dB;
# this integration allows up to +10 dB but still *defaults* to -10 dB, so the
# louder range is only reachable by deliberately raising the limit.
DEFAULT_VOLUME_MIN_DB: Final = -97.5
DEFAULT_VOLUME_MAX_DB: Final = -10.0
HARDWARE_VOLUME_MIN_DB: Final = -97.5
HARDWARE_VOLUME_MAX_DB: Final = 10.0
VOLUME_STEP_DB: Final = 0.5

UDP_PORT_STATUS: Final = 45454
UDP_PORT_COMMAND: Final = 45455
# Frame length varies by firmware: an Expert 200 broadcasts 345 bytes where other
# units send 512. Only the fields up to byte 310 are decoded, so accept anything
# long enough to carry them and read into a buffer large enough not to truncate.
STATUS_PACKET_SIZE: Final = 512
STATUS_PACKET_MIN_SIZE: Final = 311
RECEIVE_BUFFER_SIZE: Final = 2048
COMMAND_PACKET_SIZE: Final = 142
STATUS_TIMEOUT_SECONDS: Final = 2.0
DISCOVERY_TIMEOUT_SECONDS: Final = 2.0
SCAN_MAX_DEVICES: Final = 20
# The amplifier broadcasts at roughly 10 Hz, so state arrives by push. After
# this long without a single decodable datagram the entity reports idle: the
# integration is working and simply has nothing to report, which is different
# from being unable to reach it at all.
IDLE_AFTER_SECONDS: Final = 10.0

MANUFACTURER: Final = "Devialet"
MODEL: Final = "Expert (non-Pro)"

SERVICE_SET_VOLUME_DB: Final = "set_volume_db"
