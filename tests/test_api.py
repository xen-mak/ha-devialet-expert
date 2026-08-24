"""Unit tests for the self-contained Devialet UDP protocol implementation."""

from __future__ import annotations

import pathlib
import sys
import types
import unittest
from unittest.mock import patch

COMPONENTS_PATH = pathlib.Path(__file__).parents[1] / "custom_components"
PACKAGE_PATH = COMPONENTS_PATH / "devialet_expert"
package = types.ModuleType("devialet_expert")
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("devialet_expert", package)

from devialet_expert import api  # noqa: E402


class FakeCommandSocket:
    """Record UDP command payloads without using the network."""

    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False

    def sendto(self, data: bytes, address: tuple[str, int]) -> None:
        self.sent.append((bytes(data), address))

    def close(self) -> None:
        self.closed = True


class DevialetProtocolTestCase(unittest.TestCase):
    """Verify framing details ported from the upstream Devimote implementation."""

    @staticmethod
    def _status_packet() -> bytes:
        packet = bytearray(512)
        packet[19:26] = b"TestAmp"
        for index in range(15):
            packet[52 + index * 17] = ord("0")
        packet[52] = ord("1")
        packet[53:69] = b"Phono".ljust(16, b" ")
        packet[52 + 2 * 17] = ord("1")
        packet[53 + 2 * 17 : 69 + 2 * 17] = b"Toslink".ljust(16, b" ")
        packet[307] = 0x80
        packet[308] = (2 << 2) | 0x02
        packet[310] = 175  # (175 - 195) / 2 = -10 dB
        checksum = api.crc16(packet[:-2])
        packet[-2] = checksum >> 8
        packet[-1] = checksum & 0xFF
        return bytes(packet)

    def test_crc16_known_check_value(self) -> None:
        """CRC-16/CCITT-FALSE must match its canonical check vector."""
        self.assertEqual(api.crc16(b"123456789"), 0x29B1)

    def test_decode_status_packet(self) -> None:
        """A valid status broadcast exposes all user-required state."""
        status = api.decode_status_packet(self._status_packet(), "192.168.1.50")
        self.assertEqual(status["dev_name"], "TestAmp")
        self.assertEqual(status["ip"], "192.168.1.50")
        self.assertEqual(status["ch_list"], {0: "Phono", 2: "Toslink"})
        self.assertTrue(status["power"])
        self.assertTrue(status["muted"])
        self.assertEqual(status["channel"], 2)
        self.assertEqual(status["raw_volume"], 175)
        self.assertEqual(status["volume_db"], -10.0)
        self.assertTrue(status["crc_ok"])

    def test_invalid_packet_size_is_rejected(self) -> None:
        """Short datagrams cannot be mistaken for amplifier status."""
        with self.assertRaises(api.DevialetProtocolError):
            api.decode_status_packet(b"too short", "192.168.1.50")

    def test_high_source_channel_preserves_upstream_low_byte_rule(self) -> None:
        """Channels above seven use the original Devimote special low-byte encoding."""
        sock = FakeCommandSocket()
        with patch.object(api.socket, "socket", return_value=sock):
            api.DevialetClient("192.168.1.50").set_source(12)

        self.assertEqual(len(sock.sent), 4)
        payload, address = sock.sent[0]
        self.assertEqual(address, ("192.168.1.50", 45455))
        self.assertEqual(payload[:2], b"Dr")
        self.assertEqual(payload[6], 0)
        self.assertEqual(payload[7], 0x05)
        self.assertEqual(payload[8], 0x41)
        self.assertEqual(payload[9], 0x40)
        self.assertEqual(api.crc16(payload[:12]), (payload[12] << 8) | payload[13])

    def test_explicit_power_command_sends_requested_state(self) -> None:
        """On/off commands do not depend on stale toggle state."""
        sock = FakeCommandSocket()
        with patch.object(api.socket, "socket", return_value=sock):
            api.DevialetClient("192.168.1.50").set_power(True)

        payload, _ = sock.sent[0]
        self.assertEqual(payload[6], 1)
        self.assertEqual(payload[7], 0x01)


if __name__ == "__main__":
    unittest.main()
