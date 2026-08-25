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


class FakeStatusSocket:
    """Replay status broadcasts without opening a UDP port."""

    def __init__(self, responses: list[tuple[bytes, tuple[str, int]]]) -> None:
        self.responses = responses
        self.closed = False

    def settimeout(self, _timeout: float) -> None:
        """Accept the client timeout setting."""

    def recvfrom(self, _size: int) -> tuple[bytes, tuple[str, int]]:
        """Return a queued broadcast or simulate a receive timeout."""
        if not self.responses:
            raise TimeoutError
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


class DevialetProtocolTestCase(unittest.TestCase):
    """Verify framing details ported from the upstream Devimote implementation."""

    @staticmethod
    def _status_packet(size: int = 512, phono_flag: bytes = b"1") -> bytes:
        packet = bytearray(size)
        packet[19:26] = b"TestAmp"
        for index in range(15):
            packet[52 + index * 17] = ord("0")
        packet[52] = ord(phono_flag)
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

    def test_status_crc_mismatch_is_diagnostic_only(self) -> None:
        """A bad status CRC is reported but does not make the frame undecodable."""
        packet = bytearray(self._status_packet())
        packet[-1] ^= 0xFF
        status = api.decode_status_packet(bytes(packet), "192.168.1.50")
        self.assertTrue(status["connected"])
        self.assertFalse(status["crc_ok"])

    def test_client_accepts_status_with_crc_mismatch(self) -> None:
        """The receiver follows upstream DeviMote and accepts a decodable bad-CRC frame."""
        packet = bytearray(self._status_packet())
        packet[-1] ^= 0xFF
        sock = FakeStatusSocket([(bytes(packet), ("192.168.1.50", 45454))])
        getaddrinfo_result = [
            (api.socket.AF_INET, api.socket.SOCK_DGRAM, 17, "", ("192.168.1.50", 0))
        ]
        with (
            patch.object(api, "open_status_socket", return_value=sock),
            patch.object(api.socket, "getaddrinfo", return_value=getaddrinfo_result),
        ):
            status = api.DevialetClient("192.168.1.50").get_status()

        self.assertTrue(status["connected"])
        self.assertFalse(status["crc_ok"])
        self.assertTrue(sock.closed)

    def test_invalid_packet_size_is_rejected(self) -> None:
        """Short datagrams cannot be mistaken for amplifier status."""
        with self.assertRaises(api.DevialetProtocolError):
            api.decode_status_packet(b"too short", "192.168.1.50")

    def test_short_firmware_frame_is_decoded(self) -> None:
        """An Expert 200 broadcasts 345 bytes and must still be usable."""
        status = api.decode_status_packet(self._status_packet(345), "192.168.1.50")
        self.assertEqual(status["dev_name"], "TestAmp")
        self.assertEqual(status["ch_list"], {0: "Phono", 2: "Toslink"})
        self.assertEqual(status["channel"], 2)
        self.assertEqual(status["volume_db"], -10.0)
        self.assertTrue(status["connected"])

    def test_short_frame_reports_unknown_crc(self) -> None:
        """Only the canonical 512-byte frame carries a checkable trailing CRC."""
        status = api.decode_status_packet(self._status_packet(345), "192.168.1.50")
        self.assertIsNone(status["crc_ok"])

    def test_non_binary_channel_flag_enables_channel(self) -> None:
        """Upstream treats every non-zero enabled-flag digit as a selectable input."""
        packet = self._status_packet(345, phono_flag=b"4")
        status = api.decode_status_packet(packet, "192.168.1.50")
        self.assertEqual(status["ch_list"], {0: "Phono", 2: "Toslink"})

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

    @staticmethod
    def _sent_volume(db_value: float) -> tuple[float, int]:
        """Return the dB actually sent for ``db_value`` and its 16-bit wire value."""
        sock = FakeCommandSocket()
        with patch.object(api.socket, "socket", return_value=sock):
            actual = api.DevialetClient("192.168.1.50").set_volume(db_value)
        payload, _ = sock.sent[0]
        return actual, (payload[8] << 8) | payload[9]

    def test_volume_clamps_to_the_representable_range(self) -> None:
        """The status byte cannot express below -97.5 dB, and +10 dB is the ceiling."""
        self.assertEqual(self._sent_volume(-100.0)[0], -97.5)
        self.assertEqual(self._sent_volume(20.0)[0], 10.0)

    def test_positive_volume_encodes_without_the_sign_bit(self) -> None:
        """A positive dB value differs from its negative twin only by the sign bit."""
        quiet_db, quiet_wire = self._sent_volume(-10.0)
        loud_db, loud_wire = self._sent_volume(10.0)
        self.assertEqual((quiet_db, loud_db), (-10.0, 10.0))
        self.assertTrue(quiet_wire & 0x8000)
        self.assertFalse(loud_wire & 0x8000)
        self.assertEqual(quiet_wire & ~0x8000, loud_wire)

    def test_status_byte_range_matches_the_configurable_limits(self) -> None:
        """The dB floor offered in the UI is the smallest value a status byte holds."""
        self.assertEqual(api.raw_volume_to_db(0), -97.5)
        self.assertGreaterEqual(api.raw_volume_to_db(255), 10.0)

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
