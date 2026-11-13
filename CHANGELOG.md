# Changelog

All notable changes to this project are documented here.

## 3.2.6

- Add icons for devices across the integration:
  - **Network Client Devices**: Device trackers now dynamically display connection-type and link-state icons:
    - Wi-Fi clients: `mdi:wifi` when connected (home), `mdi:wifi-off` when disconnected (away).
    - Ethernet clients: `mdi:lan-connect` when connected (home), `mdi:lan-disconnect` when disconnected (away).
    - Replaces the default Home Assistant person silhouette (`mdi:account`) across device cards, entity rows, and dashboards.
  - **Router & Mesh Repeater Devices**:
    - Added device translation keys (`translation_key`) to router and mesh repeater device registry entries with English and Spanish localizations.
    - Added `icons.json` icon mappings for `device_tracker` and `signal_strength` (`mdi:wifi`).
    - Refined router reachability binary sensor icons: default `mdi:router-wireless`, off `mdi:router-wireless-off`.
    - Refined mesh repeater link status binary sensor icons: default `mdi:access-point-network`, off `mdi:access-point-network-off`.

## 3.2.5

- Add comprehensive router telemetry and service health metrics for SSH polling mode (strictly gated to SSH to avoid web polling overhead):
  - **Main SoC & Wi-Fi Temperatures**: `Main SoC temperature`, `Wi-Fi 2.4 GHz temperature`, and `Wi-Fi 5 GHz temperature` sensors parsed from `show temperature`.
  - **Optical Power Telemetry**: `Optical RX power` and `Optical TX power` sensors (dBm) parsed from `show primary_diagnosis`.
  - **WAN & Voice Service Health**: `Internet service`, `PPPoE connection`, `VoIP service`, and `SIP registration` connectivity binary sensors, plus `IPTV service status`, `Public IP`, and `Registered phone number` diagnostic sensors.
  - **Mesh Repeater Telemetry**: When a mesh repeater is detected, expose `Link status` binary sensor, `Backhaul band` sensor (2.4 GHz vs 5 GHz), and `Upstream BSSID` sensor attached directly to the Repeater device in Home Assistant.
- Automatic redaction of sensitive WAN diagnostics (public IP and registered telephone number) from diagnostic logs and captured output.

## 3.2.4

- Fix Wi-Fi channel sensors (`Channel 2.4 GHz`, `Channel 5 GHz`) for SSH polling mode: query `show wifi` and `show wifi_plus` to retrieve active operating channels (e.g. Channel 6 and Channel 36).
- Automatically redact Wi-Fi pre-shared keys and passwords from captured command output to ensure credentials are never stored in memory or exposed in diagnostic exports.
- Preserve discovered radio channels in coordinator cache between device map update polls.

## 3.2.3

- Fix memory usage calculation for Askey Linux `show sys_info`: compute accurate used memory percentage from `commitLimit` and `freeMem` counters (eliminating erroneous 499,972% readings).
- Enhance hostname extraction from `show map_info` DHCP table: extract device hostnames from multi-word Wi-Fi lines, Ethernet rows (resolving devices like SynHome), and station tables.
- Fall back cleanly to device MAC address when no hostname is broadcast to prevent `dynamic (XX:XX)` naming.

## 3.2.2

- Fix device hostname extraction in SSH `show map_info`: properly extract device names (e.g. iPhone, MacBook) from `wifi station_info` and `eth_device` sections.
- Filter out DHCP lease keywords (`dynamic`, `static`) to prevent devices from being erroneously named `dynamic (XX:XX)`.
- Default to MAC address when a device does not broadcast an mDNS/DHCP hostname.

## 3.2.1

- Ensure SSH process and connection channels are cleanly closed and awaited (`wait_closed()`) during integration unload, reload, and reconnections.
- Bind connection object immediately on connect to prevent socket leaks if process creation or prompt handshake times out.
- Add fallback to `conn.abort()` if connection termination times out.

## 3.2.0

- Add optional SSH polling method using the router's restricted CLI (`aspsh` / `Reduced_CLI_HGU_v28`) to eliminate router-side web server memory leaks.
- Interactive SSH PTY terminal integration with persistent session reuse and automatic reconnection on dropped channels.
- Parse `show map_info` for mesh topology (router vs repeater, 2.4 GHz vs 5 GHz bands), client signal RSSI, wired Ethernet devices, and DHCP hostnames.
- Parse `show sys_info` for router uptime, CPU usage, and memory usage metrics.
- Enforce strict read-only command allow-listing to guarantee sensitive router data and Wi-Fi credentials are never queried or exposed over SSH.
- Add setup flow and options flow UI support for selecting between Web and SSH polling, with configurable SSH port, username, password, and private key file.
- Redact SSH credentials and sanitize raw SSH output in Home Assistant diagnostics dumps.

## 3.1.1

- Ensure device trackers are enabled by default on initial install and updates until the user customizes their selection in Configure options.
- Automatically restore integration-disabled device trackers on setup so they appear in Home Assistant states immediately without requiring manual configuration.
- Prevent trackers assigned to a Person in Home Assistant from being inadvertently disabled.

## 3.1.0

- Add interactive device picker to **Configure** options (`Settings → Devices & services → Movistar Askey Router → Configure`), allowing users to select exactly which devices (Wi-Fi, Ethernet, repeater) to track for presence.
- Automatically enable presence trackers for selected devices and keep unselected devices disabled to eliminate entity clutter, state churn, and database noise.
- Companion client sensors in `follow_tracker` mode now seamlessly follow the device picker selection.
- Add test suite for config flow and options flow.

## 3.0.1

- Enable device tracker entities by default for all connected clients, allowing immediate assignment to a Person for presence tracking in Home Assistant.
- Fix options update handler to always reload the config entry so newly enabled client entities take effect immediately without needing a manual restart.
- Automatically re-enable any device trackers previously disabled by the integration.
- Adopt Home Assistant 2026.11 modern `ScannerEntity` standard (`has_entity_name = True`, inheriting the device name).
- Add comprehensive test suite for the device tracker platform.

## 3.0.0

- Migrate integration domain from `movistar_rft8115vw` to `movistar_askey` (`custom_components/movistar_askey`) to resolve domain conflicts with `luis-garza/movistar_rft8115vw` in HACS default catalog.
- Update bus event names from `movistar_rft8115vw_*` to `movistar_askey_router_rebooted` and `movistar_askey_client_roamed`.
- Update logger namespace to `custom_components.movistar_askey`.
- Add migration guide in `README.md` for users upgrading from 2.x custom repository installs.

## 2.2.4

- Deduplicate roaming logbook entries: remove `client_roamed` from the router's
  event entity so client roams only appear once under their own device activity
  with full transition details.
- Reserve the router event entity strictly for router lifecycle events
  (`rebooted`).

## 2.2.3

- Link client entities and access points in roam events and logbook entries:
  clicking the logbook entry navigates to the client entity, and the message
  describes transit between access points (for example `roamed from router 5 GHz
  to repeater`).
- Preserve event context on the router event entity so Home Assistant's
  Activity logbook shows the triggering cause instead of "No cause was
  recorded for this activity".
- Dynamic icon on the router event entity (`mdi:wifi-sync` for client roams,
  `mdi:restart` for reboots), restored across Home Assistant restarts.

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
