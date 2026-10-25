# Changelog

All notable changes to this project are documented here.

## 2.2.2

- Only update client device registry entries owned exclusively by this
  integration, and use `default_name` / `default_model` in `DeviceInfo` so
  devices shared by MAC address with other integrations (such as Sonos or Hue)
  keep their own name, model and parent.
- Link repeater clients directly to the mesh repeater device on initial setup
  and first discovery.

## 2.2.1

- Bundle integration brand assets (`brand/icon.png`, `brand/icon@2x.png`,
  `brand/logo.png`, `brand/logo@2x.png`) for Home Assistant and the HACS
  default catalog.

## 2.2.0

- Roam events name the client in the logbook (for example `iPhone (F0:06)
  roamed router 5 GHz → repeater`) and link to the client device, so they
  appear in its Activity. Event data adds `device_id`, `message` and
  `roam_count`.
- Add a **Roams** counter per client and a **Client roams** total on the
  router; both survive restarts.
- Add device list and router screenshots to the README.
- Releases are automatic: merging a bumped manifest version to `main` creates
  the tag and publishes the release; no manual tagging.

## 2.1.0

First release maintained independently at
[`andyzasl/ha-movistar-askey`](https://github.com/andyzasl/ha-movistar-askey).
It includes all changes from 2.0.0-beta.4 to 2.0.0-beta.6 below, and:

- Point documentation, issue tracker and code owner to the new repository.
- Releases run the full validation (Ruff, pytest, hassfest, HACS) and check
  that the tag matches the manifest version and is on `main` before
  publishing.
- `main` holds released code only; development happens on `dev`.

Upgrading: remove the previous HACS repository (`jardenberg/ha-movistar-askey`
or `luis-garza/movistar_rft8115vw`), add this one, install, and restart. The
integration domain is unchanged, so configuration and entities are kept;
version 1 entries are migrated automatically.

## 2.0.0-beta.6

- Diagnostics describe every router endpoint the integration uses, so other
  models and firmware can be supported from a diagnostics download: HTTP
  status, errors, XML paths and field names, `Result` codes, enum values and
  value shapes, device-map columns, link field versus association table,
  login cookie names, session reuse counts, stations per access point, last
  error type and integration version. Identifying fields are always redacted.

## 2.0.0-beta.5

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
- Add a **Wi-Fi signal** sensor per Wi-Fi client (dBm) for history graphs,
  with `band` and `access_point` attributes. The **Wi-Fi signal sensors**
  option sets whether they are enabled: Manual (default), Follow tracker, or
  All. Sensors disabled by the user are never re-enabled.
- Add a **Router reachable** connectivity sensor.
- Add a **Router event** entity that records reboots; the bus event is kept.
- Raise a repair notice after three consecutive failed polls; it clears on the
  next successful poll.
- Trackers show a readable `access_point`, such as `Router 5 GHz`.
- Show where each client is connected: the device card's **Connected via**
  points to the router or to a new **Mesh repeater** device, and the model
  line shows how, for example `Wi-Fi 5 GHz · private address` or `Ethernet`.
  Both are updated on every poll. The attachment comes from the device map's
  link field (0 = router 2.4 GHz, 1 = router 5 GHz, 7 = repeater), verified on
  an RTF8316VW.
- Trackers add `node` (`router` / `repeater`) and `private_mac`.
- Add an **IP address** sensor per client; the client sensors option now
  covers both signal and IP sensors.
- Add a **Devices on repeater** sensor.
- The **Router event** entity also records `client_roamed` (bus event
  `movistar_rft8115vw_client_roamed`) when a client changes node or band.
- Make duplicated client names unique with a MAC suffix, for example
  `iPhone (81:7E)`. Names set in Home Assistant are kept.
- The device model line starts with the node: `Router · Wi-Fi 5 GHz ·
  private address`, `Repeater · Wi-Fi`.
- Add a **Person** sensor per client and a `person` tracker attribute, listing
  the persons that use the client's tracker.
- Apply option changes with one reload instead of two when client sensors are
  enabled.
- Diagnostics include client counts per node and device-map link values.
- Release notes are taken from this changelog.

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
