"""Local UDP client for Devialet Expert non-Pro amplifiers.

The wire protocol is based on the GPL-3.0-or-later Devimote project by
Dimitris Lampridis and Renaud Bruyeron. This module keeps the protocol
implementation self-contained so Home Assistant can call it in its executor.
"""

from __future__ import annotations

import binascii
import logging
import math
import socket
import struct
import time
from collections.abc import Mapping
from typing import Final

from .const import (
    COMMAND_PACKET_SIZE,
    DISCOVERY_TIMEOUT_SECONDS,
    HARDWARE_VOLUME_MAX_DB,
    HARDWARE_VOLUME_MIN_DB,
    RECEIVE_BUFFER_SIZE,
    SCAN_MAX_DEVICES,
    STATUS_PACKET_MIN_SIZE,
    STATUS_PACKET_SIZE,
    STATUS_TIMEOUT_SECONDS,
    UDP_PORT_COMMAND,
    UDP_PORT_STATUS,
    VOLUME_STEP_DB,
)

_LOGGER = logging.getLogger(__name__)

_COMMAND_HEADER: Final = (0x44, 0x72)


class DevialetError(Exception):
    """Base exception for Devialet Expert communication errors."""


class DevialetConnectionError(DevialetError):
    """Raised when a status broadcast cannot be read from the target amplifier."""


class DevialetProtocolError(DevialetError):
    """Raised when an invalid command or status packet is encountered."""


def crc16(data: bytes | bytearray) -> int:
    """Return the protocol's CRC-16/CCITT-FALSE checksum."""
    return binascii.crc_hqx(data, 0xFFFF)


def raw_volume_to_db(raw_value: int) -> float:
    """Convert the status packet's volume byte to dB."""
    if not 0 <= raw_value <= 255:
        raise DevialetProtocolError(f"Invalid raw volume: {raw_value}")
    return (raw_value - 195.0) / 2.0


def _db_to_protocol_value(db_value: float) -> int:
    """Convert a dB magnitude to the 16-bit representation used on the wire."""
    db_abs = math.fabs(db_value)
    if db_abs == 0:
        return 0
    if db_abs == VOLUME_STEP_DB:
        return 0x3F00
    return (256 >> math.ceil(1 + math.log(db_abs, 2))) + _db_to_protocol_value(
        db_abs - VOLUME_STEP_DB
    )


def _decode_text(value: bytes) -> str:
    """Decode a fixed-width UTF-8 field, removing wire padding."""
    return value.decode("utf-8", errors="replace").rstrip("\x00 ")


def _channel_is_enabled(flag: int) -> bool:
    """Report whether a channel's ASCII enabled-flag byte marks it as selectable.

    The flag is not limited to ``0``/``1``: an Expert 200 reports ``4`` for its
    phono input. Upstream DeviMote treats every non-zero digit as enabled.
    """
    character = chr(flag)
    return character.isdigit() and character != "0"


def decode_status_packet(data: bytes, address: str) -> dict[str, object]:
    """Decode a Devialet status packet into Home Assistant-ready data."""
    if len(data) < STATUS_PACKET_MIN_SIZE:
        raise DevialetProtocolError(
            f"Expected at least {STATUS_PACKET_MIN_SIZE} status bytes, "
            f"received {len(data)} bytes"
        )

    channel_list: dict[int, str] = {}
    for index in range(15):
        offset = 52 + index * 17
        if _channel_is_enabled(data[offset]):
            channel_list[index] = _decode_text(data[offset + 1 : offset + 17])

    return {
        "dev_name": _decode_text(data[19:50]) or "Devialet Expert",
        "ip": address,
        "ch_list": channel_list,
        "power": bool(data[307] & 0x80),
        "muted": bool(data[308] & 0x02),
        "channel": (data[308] & 0x3C) >> 2,
        "raw_volume": data[310],
        "volume_db": raw_volume_to_db(data[310]),
        "connected": True,
        # Upstream DeviMote records this result but does not reject the status packet.
        # Only the canonical 512-byte frame is known to end in this checksum, so
        # shorter firmware variants report ``None`` rather than a bogus failure.
        "crc_ok": (
            crc16(data[:-2]) == struct.unpack(">H", data[-2:])[0]
            if len(data) == STATUS_PACKET_SIZE
            else None
        ),
    }


def open_status_socket() -> socket.socket:
    """Open a reusable socket bound to the amplifier's broadcast status port.

    ``SO_REUSEADDR`` alone is deliberate: Linux hands every socket bound to the
    port its own copy of a broadcast datagram, so a config flow can listen while
    a configured entry's push listener already holds the same port. Adding
    ``SO_REUSEPORT`` would instead group the sockets and hand each datagram to
    only one of them.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", UDP_PORT_STATUS))
    return sock


def resolve_addresses(host: str) -> set[str]:
    """Resolve ``host`` to the set of addresses its datagrams may originate from."""
    try:
        return {addr[4][0] for addr in socket.getaddrinfo(host, None)}
    except socket.gaierror as err:
        raise DevialetConnectionError(f"Cannot resolve {host}") from err


class DevialetClient:
    """Blocking UDP client for one Devialet Expert non-Pro amplifier."""

    def __init__(self, host: str) -> None:
        """Initialize a client that will accept status broadcasts from ``host``."""
        self.host = host
        self._packet_counter = 0

    @staticmethod
    def scan(
        timeout: float = DISCOVERY_TIMEOUT_SECONDS,
        max_devices: int = SCAN_MAX_DEVICES,
    ) -> list[dict[str, object]]:
        """Collect decodable Devialet status broadcasts visible on the local network."""
        discovered: dict[str, dict[str, object]] = {}
        deadline = time.monotonic() + timeout
        try:
            sock = open_status_socket()
        except OSError:
            return []
        try:
            while time.monotonic() < deadline and len(discovered) < max_devices:
                sock.settimeout(max(0.05, deadline - time.monotonic()))
                try:
                    data, addr = sock.recvfrom(RECEIVE_BUFFER_SIZE)
                except TimeoutError:
                    break
                try:
                    status = decode_status_packet(data, addr[0])
                except DevialetProtocolError as err:
                    _LOGGER.debug("Ignoring datagram from %s: %s", addr[0], err)
                    continue
                discovered[addr[0]] = status
        finally:
            sock.close()

        return list(discovered.values())


    def get_status(self, timeout: float = STATUS_TIMEOUT_SECONDS) -> dict[str, object]:
        """Receive the next decodable status broadcast from this configured host."""
        expected_addresses = resolve_addresses(self.host)

        deadline = time.monotonic() + timeout
        try:
            sock = open_status_socket()
        except OSError as err:
            raise DevialetConnectionError(
                f"Unable to listen for Devialet status broadcasts on UDP {UDP_PORT_STATUS}"
            ) from err
        try:
            while time.monotonic() < deadline:
                sock.settimeout(max(0.05, deadline - time.monotonic()))
                try:
                    data, addr = sock.recvfrom(RECEIVE_BUFFER_SIZE)
                except TimeoutError as err:
                    raise DevialetConnectionError(
                        f"No Devialet status broadcast received from {self.host}"
                    ) from err
                if addr[0] not in expected_addresses:
                    _LOGGER.debug(
                        "Ignoring status broadcast from %s while waiting for %s",
                        addr[0],
                        self.host,
                    )
                    continue
                try:
                    status = decode_status_packet(data, addr[0])
                except DevialetProtocolError as err:
                    _LOGGER.debug("Undecodable datagram from %s: %s", addr[0], err)
                    continue
                return status
        finally:
            sock.close()

        raise DevialetConnectionError(
            f"No decodable Devialet status broadcast received from {self.host}"
        )

    def set_power(self, powered: bool) -> None:
        """Set the amplifier to on or standby explicitly."""
        self._send_command(command_type=0x01, value=int(powered))

    def set_muted(self, muted: bool) -> None:
        """Set the amplifier mute state explicitly."""
        self._send_command(command_type=0x07, value=int(muted))

    def set_volume(self, db_value: float) -> float:
        """Set volume in dB and return the value actually sent to the amplifier."""
        value = round(
            min(max(float(db_value), HARDWARE_VOLUME_MIN_DB), HARDWARE_VOLUME_MAX_DB)
            / VOLUME_STEP_DB
        ) * VOLUME_STEP_DB
        protocol_value = _db_to_protocol_value(value)
        if value < 0:
            protocol_value |= 0x8000
        self._send_command(command_type=0x04, value=protocol_value)
        return value

    def set_source(self, channel: int) -> None:
        """Select an amplifier source by its protocol channel index."""
        if not 0 <= channel <= 14:
            raise DevialetProtocolError(f"Invalid source channel: {channel}")
        protocol_value = 0x4000 | (channel << 5)
        self._send_command(
            command_type=0x05,
            value=protocol_value,
            halve_source_low_byte=channel > 7,
        )

    def _send_command(
        self, command_type: int, value: int, halve_source_low_byte: bool = False
    ) -> None:
        """Build, CRC-frame, and send the command packet four times for UDP reliability."""
        data = bytearray(COMMAND_PACKET_SIZE)
        data[0], data[1] = _COMMAND_HEADER
        data[6] = (value >> 8) & 0xFF if command_type in (0x04, 0x05) else value
        data[7] = command_type
        if command_type in (0x04, 0x05):
            data[8] = (value >> 8) & 0xFF
            data[9] = (value & 0xFF) >> 1 if halve_source_low_byte else value & 0xFF
            data[6] = 0

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            for _ in range(4):
                data[3] = self._packet_counter & 0xFF
                data[5] = (self._packet_counter >> 1) & 0xFF
                self._packet_counter = (self._packet_counter + 1) & 0xFF
                checksum = crc16(data[:12])
                data[12] = (checksum >> 8) & 0xFF
                data[13] = checksum & 0xFF
                sock.sendto(data, (self.host, UDP_PORT_COMMAND))
        except OSError as err:
            raise DevialetConnectionError(
                f"Unable to send command to Devialet at {self.host}"
            ) from err
        finally:
            sock.close()


def status_summary(status: Mapping[str, object]) -> str:
    """Create a compact, non-sensitive title for config flow selection."""
    name = str(status.get("dev_name") or "Devialet Expert")
    host = str(status.get("ip") or "unknown host")
    return f"{name} ({host})"
