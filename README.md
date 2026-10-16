# Movistar Askey Router for Home Assistant

[![Validate](https://github.com/jardenberg/ha-movistar-askey/actions/workflows/validate.yaml/badge.svg)](https://github.com/jardenberg/ha-movistar-askey/actions/workflows/validate.yaml)
[![HACS custom repository](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Release](https://img.shields.io/github/v/release/jardenberg/ha-movistar-askey?include_prereleases&label=release)](https://github.com/jardenberg/ha-movistar-askey/releases)

A modern, local-polling Home Assistant integration for compatible Movistar
Askey routers. It reads the router's local-network map and exposes a router
device, a connected-device count sensor, and optional presence trackers—without
using a Movistar cloud service.

This project modernizes
[`luis-garza/movistar_rft8115vw`](https://github.com/luis-garza/movistar_rft8115vw).
Version 2 replaces Home Assistant's deprecated legacy YAML device tracker with
config entries, coordinated polling, current entity APIs, reauthentication,
options, and privacy-preserving diagnostics.

> [!WARNING]
> Version 2 is currently a prerelease. It has been tested live with a Movistar
> RTF8316VW and Home Assistant 2026.7.3, but you should keep a recent Home
> Assistant backup while testing it.

## Compatibility

| Router | Status | Notes |
| --- | --- | --- |
| **Askey RTF8316VW** | Live verified | Movistar WiFi 7 Router; hardware revision 4 tested |
| **Askey RTF8115VW** | Expected compatible | Original integration target; uses the same local web-map protocol |
| Other Movistar routers | Unknown | Do not assume compatibility from branding alone |

The integration expects the router's local web interface at an IPv4 address,
normally `192.168.1.1`. It uses the **router web-admin password**, not the Wi-Fi
password.

### Tested firmware

| Model | Hardware | Firmware | Customization | Tested |
| --- | --- | --- | --- | --- |
| Askey RTF8316VW | REV4 | `GL_g1.18_R8316_V2.19` | `TEF-ES` | Device map, session reuse, XML status endpoints (`cbListWifiAccPtAssociation`, `cbGetWifi`, `cbGetSummary`) |

The XML status endpoints (Wi-Fi details, router sensors, reboot event) are
verified only on the firmware above. Other firmware may name or nest fields
differently; the related sensors then stay empty while device tracking keeps
working. Router firmware is shown on the router device in Home Assistant;
please include it when reporting results.

## What the integration provides

- Setup and reauthentication through **Settings → Devices & services**
- Local communication directly with the router over HTTP
- One Home Assistant device representing the router
- A **Connected devices** sensor
- A current client inventory in the sensor's `devices` attribute
- One device tracker for every MAC address observed by the router
- Configurable polling and presence-grace intervals
- Diagnostics with the password, client names, IP addresses, and MAC addresses
  excluded
- English and Spanish setup text

### Entities

#### Connected devices sensor

The enabled-by-default sensor reports the number of devices in the latest
successful router poll. Its `devices` attribute contains the current name, IPv4
address, and MAC address reported for each client.

The exact entity ID is assigned by Home Assistant. A typical dashboard card is:

```yaml
type: entities
title: Local network
entities:
  - entity: sensor.movistar_askey_router_connected_devices
    name: Connected devices
```

#### Device trackers

The integration creates a tracker when it first sees a client MAC address.
Trackers are **disabled by default** to avoid filling Home Assistant with dozens
of unwanted presence entities.

Enable only the trackers you need:

1. Open **Settings → Devices & services → Entities**.
2. Select the relevant client entity.
3. Enable it in the entity settings.

Each tracker exposes the latest hostname, IPv4 address, and MAC address. A
client remains `home` for the configured presence-grace period after it stops
appearing in the router map.

Trackers also expose `connection` (`wifi` or `ethernet`), `node` (`router` or
`repeater`), `access_point` and `private_mac`. For clients associated directly
with the router's Wi-Fi, they add `band`, `ap_id`, `rssi` (dBm), `link_rate`,
`wifi_standard` and `associated_seconds`. Clients behind the mesh repeater are
not in the router's association table, so they have no band or RSSI.

#### Client devices

Each client's device card shows where it is connected:

- **Connected via** points to the router or to the **Mesh repeater** device.
- The model line shows how, for example `Wi-Fi 5 GHz · private address` or
  `Ethernet`. *Private address* means the device uses a randomized Wi-Fi MAC.

Both are updated on every poll. Duplicated names, common for Apple devices,
get a MAC suffix such as `iPhone (81:7E)`; renaming a device in Home Assistant
overrides it.

#### Router sensors

| Sensor | Notes |
| --- | --- |
| Wi-Fi clients 2.4 GHz / 5 GHz | Clients associated directly with the router; mesh backhaul links are excluded |
| Devices on repeater | Clients attached to the mesh repeater (may include the repeater itself) |
| Last boot | Diagnostic; derived from router uptime |
| CPU usage, Memory usage | Diagnostic; percent |
| Channel 2.4 GHz / 5 GHz | Diagnostic; `bandwidth_mhz` attribute |
| Last successful poll | Diagnostic; `consecutive_failures` attribute |
| Router reachable | Diagnostic binary sensor; `off` while polls fail |

The router device shows the firmware and hardware revision. These values come
from the router's XML status endpoints, verified on the RTF8316VW. On routers
without these endpoints the sensors stay empty and device tracking is not
affected.

#### Client sensors

Each client gets an **IP address** sensor, and each client seen on the router's
Wi-Fi also gets a **Wi-Fi signal** sensor (dBm). Both are attached to the
client device. The **Client sensors** option controls whether they are
enabled:

| Mode | Behavior |
| --- | --- |
| Manual (default) | Created disabled; enable the ones you want |
| Follow tracker | A client's sensors are enabled while its device tracker is enabled |
| All | Every client's sensors are enabled |

Sensors you disabled yourself are never re-enabled. After a sensor is enabled,
Home Assistant reloads the integration about 30 seconds later to activate it.
The signal value is empty while the client is away or connected through the
mesh repeater.

#### Events

The **Router event** entity records:

- `rebooted` when router uptime goes backwards between two polls (bus event
  `movistar_rft8115vw_router_rebooted` with `uptime_seconds` and
  `previous_uptime_seconds`);
- `client_roamed` when a client present in two consecutive polls changes node
  (router ⇄ repeater) or band (bus event `movistar_rft8115vw_client_roamed`
  with `mac`, `name`, `from_node`, `to_node`, `from_band`, `to_band`).

#### Repairs

After three consecutive failed polls, a notice appears under **Settings →
Repairs**. It clears automatically after the next successful poll.

## Installation with HACS

Until version 2 is published as a stable release, install it as a custom HACS
repository:

1. Open **HACS → Integrations**.
2. Open the menu and choose **Custom repositories**.
3. Add `https://github.com/jardenberg/ha-movistar-askey` with category
   **Integration**.
4. Open **Movistar Askey Router** in HACS.
5. Choose the latest prerelease version and install it.
6. Restart Home Assistant.

Then configure the router:

1. Open **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **Movistar Askey Router**.
4. Enter the router IP address and its web-admin password.

No username is required by the supported router interface.

## Migrating from the UI-based version 1 integration

Config entries created through the UI by
[`luis-garza/movistar_rft8115vw`](https://github.com/luis-garza/movistar_rft8115vw)
are migrated automatically on first start: the polling interval option is
carried over (raised to at least 30 seconds), and existing device trackers keep
their entity IDs and person assignments. No reconfiguration is needed.

## Migrating from the legacy YAML tracker

The old integration used a YAML platform similar to:

```yaml
device_tracker:
  - platform: movistar_rft8115vw
    host: 192.168.1.1
    password: !secret movistar_router_password
```

To migrate:

1. Make a Home Assistant backup.
2. Remove the legacy `movistar_rft8115vw` block from `configuration.yaml`.
3. Check the Home Assistant configuration.
4. Install version 2 through HACS and restart Home Assistant.
5. Add **Movistar Askey Router** through **Settings → Devices & services**.
6. Enable only the client trackers used by your automations or presence logic.

After setup, the password is stored in Home Assistant's config-entry storage.
It does not need to remain in `secrets.yaml` unless something else still uses
that secret.

The deprecated legacy tracker warning is removed because version 2 uses modern
config-entry entities. Existing tracker entity IDs are not guaranteed to carry
over automatically; verify presence automations after migration.

## Options

Open **Settings → Devices & services → Movistar Askey Router**. On the entry
row, select the gear icon (or **⋮ → Options**, depending on the Home Assistant
version).

| Option | Default | Allowed range | Purpose |
| --- | ---: | ---: | --- |
| Polling interval | 300 seconds | 30–3600 seconds | How often the router map is refreshed |
| Presence grace period | 600 seconds | 0–3600 seconds | How long a missing client remains `home` |
| Client sensors | Manual | Manual, Follow tracker, All | Which per-client signal and IP sensors are enabled |

Internally, the effective presence grace period is never shorter than the
polling interval.

To change the router address or password, use **⋮ → Reconfigure** on the same
entry row. Existing entities are kept.

## Troubleshooting

### The router rejects the password

- Confirm that the same password works at `http://192.168.1.1`.
- Use the **router administration** password, not the Wi-Fi password.
- Confirm that the router model is compatible.
- If a setup attempt was interrupted, close the dialog, wait briefly, refresh
  **Devices & services**, and try again.

Version `2.0.0-beta.3` includes the RTF8316VW authentication fix and registers
the parent router before client trackers, satisfying Home Assistant's strict
device-registry ordering requirements.

Version `2.0.0-beta.2` fixed a false authentication failure on the RTF8316VW:
its authenticated network-map page still references the login endpoint.

### The integration is unavailable after restart

The router must be reachable from Home Assistant. Verify the configured IP and
that Home Assistant is on the same routed local network. Startup connection
failures are retried by Home Assistant.

### Short router outages

A failed poll is treated as a gap in data collection, not as clients leaving.
Entities stay available for up to two consecutive failed polls; trackers keep
their state for the presence grace period after their last successful
observation. After the third consecutive failure the entities become
unavailable. The diagnostic **Last successful poll** sensor and its
`consecutive_failures` attribute show the current state.

The integration keeps its router web session between polls. Logging in to the
router web interface from a browser can still end that session; the
integration then logs in again on the next poll.

### A client tracker is missing

The router must report the client at least once before its tracker can be
created. After the next successful poll, find disabled entities under
**Settings → Devices & services → Entities**.

### Logs and diagnostics

- Logs: **Settings → System → Logs**
- Diagnostics: open the integration entry menu and choose **Download
  diagnostics**

Diagnostics include availability, device count, and timing options. They do not
include credentials or the client inventory.

## Privacy and security

- Communication stays on the local network.
- The integration does not call Movistar cloud APIs.
- The router admin password is stored by Home Assistant as config-entry data.
- Home Assistant backups may contain config-entry credentials; protect and
  encrypt backups accordingly.
- Client names, IP addresses, and MAC addresses are intentionally removed from
  downloaded diagnostics.

The router's local web interface uses HTTP rather than HTTPS. Keep Home
Assistant and the router on a trusted LAN.

## Development

The validation workflow runs Ruff, pytest, Home Assistant hassfest, and HACS
validation.

```bash
python -m pip install -r requirements.txt
python -m ruff check .
python -m ruff format . --check
python -m pytest
```

The router parser has no cloud dependency. When changing authentication logic,
add a regression fixture that reflects the HTML returned by the relevant router
firmware without committing passwords or a real client inventory.

## Release status

See [CHANGELOG.md](CHANGELOG.md) for version history and
[GitHub Releases](https://github.com/jardenberg/ha-movistar-askey/releases) for
installable packages.

## License and attribution

Licensed under GPL-3.0, following the upstream project. The original integration
concept and parser remain credited to their respective contributors.
