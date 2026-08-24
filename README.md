# Devialet Expert (non-Pro) for Home Assistant

[![Validate HACS integration](https://github.com/xen-mak/devialet-expert-hacs/actions/workflows/validate.yml/badge.svg)](https://github.com/xen-mak/devialet-expert-hacs/actions/workflows/validate.yml)

A local Home Assistant `media_player` integration for **Devialet Expert non-Pro amplifiers manufactured before the Core Infinity board**. It is based on the reverse-engineered local UDP protocol implemented by [DeviMote](https://github.com/gnulabis/devimote). The integration does not require a cloud account, password, or external service.[1]

> **Compatibility:** This integration supports only the Devialet Expert non-Pro hardware covered by DeviMote. It has not been validated for Pro models or units with a Core Infinity board.[1]

## Features

Each configured amplifier is exposed as one Home Assistant `media_player` entity. Its properties use the latest cached UDP status packet rather than performing network I/O while Home Assistant renders the entity, as recommended by the Home Assistant media player interface.[2]

| Requirement | Home Assistant feature | Implementation |
| --- | --- | --- |
| Volume with limits | `media_player.volume_set` and the standard volume slider | Configurable minimum and maximum dB values; 0.5 dB amplifier resolution |
| Mute and unmute | `media_player.volume_mute` | Sends an explicit target state instead of a state-dependent toggle |
| Source list and source selection | `media_player.select_source` | Lists enabled amplifier inputs and maps the selected label to its protocol channel index |
| Power on and standby | `media_player.turn_on` and `media_player.turn_off` | Sends explicit power-state commands |
| Additional DeviMote data | State attributes and diagnostics | Device name, IP address, channel index, source map, dB/raw volume, CRC status, and connection status |
| Add an amplifier | UI configuration flow | Local UDP scan or manual IP address/hostname entry |

## Install with HACS

This repository follows the HACS custom-integration layout, including `hacs.json` at the repository root and the integration under `custom_components/devialet_expert/`.[3]

| Step | Action |
| --- | --- |
| 1 | Open **HACS → Integrations → the three-dot menu → Custom repositories**. |
| 2 | Add `https://github.com/xen-mak/devialet-expert-hacs`. |
| 3 | Select **Integration** as the category and click **Add**.[4] |
| 4 | Find **Devialet Expert (non-Pro)** in HACS, download it, and restart Home Assistant. |
| 5 | Go to **Settings → Devices & services → Add integration** and search for **Devialet Expert (non-Pro)**. |

For a manual installation, copy `custom_components/devialet_expert` into `<Home Assistant config>/custom_components/devialet_expert`, then restart Home Assistant.

## Add an amplifier

The configuration flow has two setup paths. Home Assistant configuration flows provide the integration's UI setup and discovery must be confirmed by the user before an entry is created.[5]

| Setup path | Use it when | What to do |
| --- | --- | --- |
| **Scan local network** | Home Assistant and the amplifier are on a network where UDP broadcasts can reach the Home Assistant host | Choose **Scan local network**, wait about five seconds, and select the discovered amplifier. |
| **Enter address manually** | The scan finds no device, the amplifier has a fixed DHCP address, or network routing blocks broadcasts | Choose **Enter address manually**, then enter the amplifier's current IPv4 address or resolvable hostname. |

The amplifier broadcasts 512-byte status packets on UDP port **45454** and accepts command packets on UDP port **45455**. This is the local protocol documented by DeviMote.[1] The Home Assistant host must be able to receive UDP broadcasts on port 45454 and send UDP traffic to port 45455 on the amplifier. When Home Assistant runs in a container, check the container network mode and firewall rules.

The observed protocol does not expose a verified immutable serial number or MAC address. The integration therefore does not use an IP address as a fake device serial number. If DHCP changes the amplifier's address, use **Reconfigure** on the integration and enter the new address or hostname.

## CRC policy and connection troubleshooting

The upstream DeviMote receiver decodes the status packet and records its CRC result, but does **not** reject a status packet merely because its CRC is not valid.[1] Starting with this release, this integration follows that behavior: **CRC is diagnostic-only for incoming status broadcasts.** A packet with an invalid or unexpected status CRC can still establish the connection, populate state, and complete the configuration flow. The `crc_ok` attribute remains available for troubleshooting.

The integration still creates the command-packet CRC required by the upstream protocol when it changes volume, mute, power, or source. Removing the command CRC would depart from the known DeviMote command framing and could cause the amplifier to ignore commands.[1]

| Symptom | Checks to perform |
| --- | --- |
| No device appears in the scan | Confirm that Home Assistant and the amplifier share a broadcast-capable network segment. Then use manual setup with the amplifier's IPv4 address. |
| Manual setup says it cannot connect | Confirm the amplifier is powered, its address is correct, UDP port 45454 reaches the Home Assistant host, and no Docker, VLAN, Wi-Fi isolation, or firewall rule blocks broadcast traffic. |
| The entity is unavailable after setup | Inspect `connected`, `crc_ok`, and `ip_address` in the entity attributes. A false `crc_ok` no longer blocks the entity; a false `connected` indicates no status datagram was received in the listening window. |
| Commands have no effect | Confirm the configured address is the amplifier's current address and that UDP port 45455 is reachable. The command CRC is intentionally retained. |

## Volume limits and dB mapping

Open the integration's **Configure** options to choose **Minimum volume (dB)** and **Maximum volume (dB)**. Defaults are **-97.5 dB** through **-10.0 dB**, the full range currently handled by the protocol implementation. Choosing a lower maximum can keep dashboards, voice assistants, and automations from setting an unsafe listening level.

The status packet's raw volume byte is converted as follows:

```text
volume_db = (raw_volume - 195) / 2
```

`media_player.volume_level` is normalized to 0.0–1.0 within the configured dB boundaries, as required by the Home Assistant media player interface.[2] When the physical remote or amplifier changes volume outside Home Assistant, `volume_db` and `raw_volume` still expose the actual reported value; the Home Assistant slider itself is clamped to 0% or 100% at the configured bounds.

## State attributes and diagnostics

The integration listens for a recent status broadcast every two seconds. All decoded values are exposed as Home Assistant state attributes for advanced automations.

| Attribute | Meaning |
| --- | --- |
| `device_name`, `ip_address` | Device name and sender address from the latest broadcast |
| `channel_index`, `sources_by_channel` | Current input and the full protocol-channel-to-source-name mapping |
| `volume_db`, `raw_volume` | Reported physical volume in dB and its raw packet byte |
| `crc_ok`, `connected` | Latest packet integrity result and whether a status datagram was received |
| `configured_host` | Address or hostname entered in the integration configuration |
| `volume_min_db`, `volume_max_db` | dB limits applied to the Home Assistant slider and write commands |

Use **Settings → Devices & services → Devialet Expert (non-Pro) → Download diagnostics** to obtain a sanitized support snapshot. The configured and reported host information is redacted.

## Development, validation, and license

The repository includes protocol tests that do not need a physical amplifier. They cover CRC-16/CCITT-FALSE, status decoding, explicit power commands, and high source-channel encoding.

```bash
python3 -m unittest discover -s tests -v
```

The HACS validation workflow in `.github/workflows/validate.yml` checks the repository structure using the official HACS action.[6] The protocol implementation is derived from GPL-3.0-or-later DeviMote code, so this project is distributed under **GPL-3.0-or-later**. See [LICENSE](LICENSE).

## References

[1] [gnulabis/devimote — DeviMote GitHub repository](https://github.com/gnulabis/devimote)

[2] [Home Assistant Developer Docs — Media player entity](https://developers.home-assistant.io/docs/core/entity/media-player/)

[3] [HACS — Publishing integrations](https://www.hacs.xyz/docs/publish/integration/)

[4] [HACS — Custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)

[5] [Home Assistant Developer Docs — Config flow](https://developers.home-assistant.io/docs/core/integration/config_flow/)

[6] [HACS — GitHub Action validation](https://www.hacs.xyz/docs/publish/action/)
