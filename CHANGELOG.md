# Changelog

All notable changes to this modernization fork are documented here.

## 2.0.0-beta.4

- Migrate config entries from the version 1 integration
  (`luis-garza/movistar_rft8115vw`): rename `interval_seconds` to
  `scan_interval` within the new limits, and convert tracker unique IDs from
  lower-case to upper-case MAC addresses so existing entities, entity IDs and
  person assignments are kept. Previously Home Assistant reported
  "Migration handler not found" and did not load the entry.
- Add Wi-Fi, radio and router summary data to diagnostics, without client
  identifiers.
- Options form: number fields in seconds with help text.
- Add **Reconfigure** to change the router address or password without
  removing the integration.
- Translate entity names (English and Spanish) and move icons to
  `icons.json`. Existing entity IDs are unchanged.
- Add a **Wi-Fi signal** sensor per Wi-Fi client (dBm, disabled by default)
  for history graphs, with `band` and `access_point` attributes.
- Add a **Router reachable** connectivity sensor.
- Add a **Router event** entity that records reboots; the bus event is kept.
- Raise a repair notice after three consecutive failed polls; it clears on the
  next successful poll.
- Trackers show a readable `access_point`, such as `Router 5 GHz`.

- Reuse the router web session between polls and log in again only when the
  router no longer accepts it. Polling no longer displaces other router web
  sessions on every scan.
- Report invalid credentials only when a fresh login fails, so an expired
  session no longer starts reauthentication.
- Keep entities available through up to two consecutive failed polls. Trackers
  fall back to the presence grace period instead of turning `unavailable`
  together, which previously could empty `zone.home` and trigger away
  automations.
- Add a diagnostic **Last successful poll** sensor with a
  `consecutive_failures` attribute, and include both values in diagnostics.
- Add Wi-Fi details to client trackers from the router's association table:
  `connection`, `band`, `ap_id`, `rssi`, `link_rate`, `wifi_standard` and
  `associated_seconds`.
- Add router sensors: **Last boot**, **CPU usage**, **Memory usage**,
  **Wi-Fi clients 2.4 GHz / 5 GHz**, and **Channel 2.4 GHz / 5 GHz** with a
  `bandwidth_mhz` attribute.
- Report router firmware and hardware revision on the router device.
- Fire a `movistar_rft8115vw_router_rebooted` event when router uptime goes
  backwards.
- Read the status endpoints best effort: if one fails, the device-map poll
  still succeeds.

## 2.0.0-beta.3

- Register the router device before creating client trackers.
- Use one shared router identifier for the sensor and every client `via_device`.
- Resolve the Home Assistant device-registry warning that the parent device did
  not yet exist during first setup.

## 2.0.0-beta.2

- Fix false password rejection on the live-tested Askey RTF8316VW.
- Accept an authenticated network-map page even when its HTML references the
  router login endpoint.
- Add regression coverage for the RTF8316VW response pattern.
- Rewrite the repository documentation for the modern config-entry integration.

## 2.0.0-beta.1

- Replace the deprecated legacy YAML device tracker with a config-entry
  integration.
- Add UI setup and reauthentication.
- Add coordinated local polling and configurable timing options.
- Add a router device and connected-device count sensor.
- Create disabled-by-default client device trackers dynamically.
- Add privacy-preserving diagnostics.
- Add English and Spanish setup text.
- Add Ruff, pytest, hassfest, and HACS validation workflows.

## 1.0.0

- Legacy YAML device tracker inherited from
  [`luis-garza/movistar_rft8115vw`](https://github.com/luis-garza/movistar_rft8115vw).
