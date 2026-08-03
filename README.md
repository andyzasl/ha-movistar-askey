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

Open the integration's menu under **Settings → Devices & services** and choose
**Configure**.

| Option | Default | Allowed range | Purpose |
| --- | ---: | ---: | --- |
| Polling interval | 300 seconds | 30–3600 seconds | How often the router map is refreshed |
| Presence grace period | 600 seconds | 0–3600 seconds | How long a missing client remains `home` |

Internally, the effective presence grace period is never shorter than the
polling interval.

## Troubleshooting

### The router rejects the password

- Confirm that the same password works at `http://192.168.1.1`.
- Use the **router administration** password, not the Wi-Fi password.
- Confirm that the router model is compatible.
- If a setup attempt was interrupted, close the dialog, wait briefly, refresh
  **Devices & services**, and try again.

Version `2.0.0-beta.2` fixes a false authentication failure on the RTF8316VW:
its authenticated network-map page still references the login endpoint.

### The integration is unavailable after restart

The router must be reachable from Home Assistant. Verify the configured IP and
that Home Assistant is on the same routed local network. Startup connection
failures are retried by Home Assistant.

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
