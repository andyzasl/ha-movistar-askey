# Movistar Askey Router for Home Assistant

A modern, local-polling Home Assistant integration for compatible Movistar
Askey routers. It currently supports the web interface used by the
**RTF8115VW** and the **RTF8316VW** (Movistar WiFi 7 Router).

The project is a modernization fork of
[`luis-garza/movistar_rft8115vw`](https://github.com/luis-garza/movistar_rft8115vw).
It preserves the proven local-network-map parser while replacing Home
Assistant's deprecated legacy device tracker with config entries and modern
entities.

> [!IMPORTANT]
> Version 2 is under active development. Keep the stable upstream integration
> installed on production systems until a tested prerelease is published.

## Planned version 2 features

- Setup and reauthentication through **Settings → Devices & services**
- Local-only communication with the router
- A router device and connected-device count sensor
- One disabled-by-default device tracker per discovered client
- Polling and presence-grace options
- A documented migration path from the legacy YAML configuration
- Privacy-preserving diagnostics
- English and Spanish setup text

## Installation for development

Add this repository to HACS as a custom integration only after a prerelease has
been published. The integration retains the domain `movistar_rft8115vw` so
existing entity history can be preserved where Home Assistant can match unique
IDs.

To move from version 1 to version 2:

1. Record the current router address and admin password.
2. Remove the old `device_tracker:` YAML block and check the configuration.
3. Install version 2 and restart Home Assistant.
4. Add **Movistar Askey Router** under **Settings → Devices & services**.
5. Enable only the individual device trackers you actually use for presence.

## Data and privacy

The integration communicates directly with the router over the local network.
The admin password is stored in Home Assistant's config entry storage. Downloaded
diagnostics exclude the password, client names, IP addresses, and MAC addresses.

## Dashboard example

The integration provides entities rather than installing a custom frontend.
A simple starting card is:

```yaml
type: entities
title: Casa Vidre network
entities:
  - entity: sensor.movistar_askey_router_connected_devices
    name: Connected devices
```

Entity IDs are assigned by Home Assistant and may differ.

## Development

```bash
python -m pytest
python -m ruff check .
python -m ruff format . --check
```

## License and attribution

Licensed under GPL-3.0, following the upstream project. Original parser and
integration concept copyright remain with their respective contributors.
