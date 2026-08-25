# Devialet Expert for Home Assistant

[![Validate HACS integration](https://github.com/xen-mak/ha-devialet-expert/actions/workflows/validate.yml/badge.svg)](https://github.com/xen-mak/ha-devialet-expert/actions/workflows/validate.yml)

## This is a rewrite of the python version of Devimote by @gnulabis

This repository is a rewrite of [**DeviMote**](https://github.com/gnulabis/devimote), the original Python implementation by [**@gnulabis**](https://github.com/gnulabis).[1] Devialet publishes no documentation for this protocol — every byte offset, every command opcode, and the volume encoding were worked out by reverse-engineering the UDP traffic with Wireshark. That is the hard part, and it was already done.

What you find here is that work rewritten as a Home Assistant integration. Sincere thanks to @gnulabis for the effort that made this rewrite possible.

## About

A local Home Assistant `media_player` integration for **Devialet Expert non-Pro amplifiers manufactured before the Core Infinity board**. It needs no cloud account, password, or external service — everything happens over UDP on your own network.

> **Compatibility:** This integration supports only the Devialet Expert non-Pro hardware covered by DeviMote. It has not been validated for Pro models or units with a Core Infinity board.[1]

## Features

Each configured amplifier is exposed as one Home Assistant `media_player` entity.

| Requirement | Home Assistant feature | Implementation |
| --- | --- | --- |
| Volume with limits | `media_player.volume_set` and the standard volume slider | Configurable minimum and maximum dB values; 0.5 dB amplifier resolution |
| Mute and unmute | `media_player.volume_mute` | Sends an explicit target state instead of a state-dependent toggle |
| Source list and source selection | `media_player.select_source` | Lists enabled amplifier inputs and maps the selected label to its protocol channel index |
| Power on and standby | `media_player.turn_on` and `media_player.turn_off` | Sends explicit power-state commands |
| Add an amplifier | UI configuration flow | One dialog combining the local UDP scan, manual IP address/hostname entry, and the volume limits |

## Install with HACS

This repository follows the HACS custom-integration layout, including `hacs.json` at the repository root and the integration under `custom_components/devialet_expert/`.[2]

| Step | Action |
| --- | --- |
| 1 | Open **HACS → Integrations → the three-dot menu → Custom repositories**. |
| 2 | Add `https://github.com/xen-mak/ha-devialet-expert`. |
| 3 | Select **Integration** as the category and click **Add**.[3] |
| 4 | Find **Devialet Expert** in HACS, download it, and restart Home Assistant. |
| 5 | Go to **Settings → Devices & services → Add integration** and search for **Devialet Expert**. |

For a manual installation, copy `custom_components/devialet_expert` into `<Home Assistant config>/custom_components/devialet_expert`, then restart Home Assistant.

## Live updates

The amplifier announces its complete state — power, volume, mute, and selected input — by broadcasting a status packet on UDP port 45454 about ten times a second. Two design choices turn that stream into a responsive entity.

**A persistent UDP listener.** The integration opens one socket when the config entry loads and keeps it open for the lifetime of the entry, decoding each datagram the moment it arrives. Nothing is scheduled and nothing is requested; the amplifier is already talking, so the integration simply listens. Turning the physical volume knob, pressing the handset, or changing the input on the front panel reaches Home Assistant in roughly a tenth of a second. This is why the integration declares itself `local_push`.

**Publishing only on change.** Most of those ten packets per second repeat the previous state verbatim. Each decoded packet is compared against the last one, and the entity is republished only when a value actually differs. Home Assistant's state machine, your automations, and the recorder therefore see one update per real change — a volume sweep produces a smooth series of updates, while an idle amplifier produces none at all.

Because state arrives continuously rather than on request, silence is meaningful in itself: if no decodable broadcast arrives for ten seconds the entity reports `idle`. It stays available and keeps its last known values — nothing has failed, the amplifier has simply stopped announcing itself — and it returns to its real state as soon as packets resume.

## Volume limits

The amplifier's volume is expressed in dB. Two settings map that onto the standard Home Assistant volume slider:

| Setting | Meaning |
| --- | --- |
| **Minimum volume (dB)** | The dB value shown as 0% on the slider |
| **Maximum volume (dB)** | The dB value shown as 100% on the slider |

| | Value |
| --- | --- |
| Selectable range | **-97.5 dB** to **+10.0 dB** |
| Defaults | **-97.5 dB** to **-10.0 dB** |
| Step | 0.5 dB |

Both are set in the dialog when you add the amplifier, and can be changed later under **Configure**. Narrowing the range gives the slider finer control over the levels you actually use, and lowering the maximum keeps dashboards, voice assistants, and automations from reaching an uncomfortable level.

> **Note:** -97.5 dB is the quietest value the amplifier can report, so no lower limit is available. Values above -10 dB are loud; the default maximum stays at -10 dB, and the louder range is only reachable by raising the limit deliberately.

## State attributes and diagnostics

Alongside the standard `media_player` properties — state, `volume_level`, `is_volume_muted`, `source`, and `source_list` — the entity exposes these attributes for automations:

| Attribute | Meaning |
| --- | --- |
| `device_name`, `ip_address` | Device name and sender address from the latest broadcast |
| `volume_db`, `raw_volume` | Reported physical volume in dB and its raw packet byte |
| `connected` | Whether a status broadcast is currently being received |
| `configured_host` | Address or hostname entered in the integration configuration |
| `volume_min_db`, `volume_max_db` | dB limits applied to the Home Assistant slider and write commands |

Use **Settings → Devices & services → Devialet Expert → Download diagnostics** to obtain a sanitized support snapshot. The configured and reported host information is redacted.

## Development, validation, and license

The repository includes protocol tests that do not need a physical amplifier. They cover CRC-16/CCITT-FALSE, status decoding, explicit power commands, high source-channel encoding, and the volume range.

```bash
python3 -m unittest discover -s tests -v
```

The HACS validation workflow in `.github/workflows/validate.yml` checks the repository structure using the official HACS action.[4] The protocol implementation is derived from GPL-3.0-or-later DeviMote code, so this project is distributed under **GPL-3.0-or-later**. See [LICENSE](LICENSE).

## References

[1] [gnulabis/devimote — DeviMote GitHub repository](https://github.com/gnulabis/devimote)

[2] [HACS — Publishing integrations](https://www.hacs.xyz/docs/publish/integration/)

[3] [HACS — Custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)

[4] [HACS — GitHub Action validation](https://www.hacs.xyz/docs/publish/action/)
