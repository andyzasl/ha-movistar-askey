# Changelog

All notable changes to this modernization fork are documented here.

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
