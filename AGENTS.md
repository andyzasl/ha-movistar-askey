# AGENTS.md — ha-movistar-askey

Continuation context and guidelines for AI coding assistants working on this repository.

---

## Project Overview

**ha-movistar-askey** is a modern [Home Assistant](https://www.home-assistant.io/) custom component (HACS integration) for Movistar (Telefónica) GPON/HGU routers manufactured by Askey (specifically **RTF8115VW**, and compatible models such as **RTF8316VW**).

* **Domain**: `movistar_rft8115vw`
* **Type**: Hub / local polling integration (`local_polling`)
* **Transport**: Local HTTP web interface scraping using `aiohttp` against endpoints like `/login.cgi`, `/device_data.cgi`, and `/status.cgi`.

---

## Core Architecture & Components

### 1. Web Client & Data Parsing (`router.py`, `status.py`)
* `MovistarAskeyClient`: Authenticates and manages HTTP sessions with the router, handling session expiration and re-login automatically.
* Extracts the active device table (`device_data.cgi`), decoding MAC, IP, interface, link status, and mesh attachment node (router vs. repeater, 2.4 GHz vs. 5 GHz).
* `RouterStatus` & `WifiClient`: Parses Wi-Fi client details (signal RSSI, band, TX/RX packets) and system metrics (CPU, RAM, uptime, firmware, hardware versions).

### 2. Coordinator (`coordinator.py`)
* `MovistarAskeyCoordinator`: Subclasses `DataUpdateCoordinator[dict[str, RouterDevice]]`.
* Periodically polls router endpoints (default: 30s) and status (default: 60s).
* Detects client roaming between access points (router 2.4 GHz, router 5 GHz, or mesh repeater) via `detect_roams(...)`.
* Maintains cumulative roam counters per client and router-wide total roams (persisted across restarts).
* Dispatches bus events:
  * `movistar_rft8115vw_client_roamed`: Fired when a client moves between nodes or bands.
  * `movistar_rft8115vw_router_rebooted`: Fired when router uptime decreases between consecutive polls.

### 3. Device Hierarchy (`device.py`)
* **Router Device**: Primary hub device representing the physical gateway.
* **Repeater Device**: Discovered mesh repeater (if present in client attachments), linked to the router.
* **Client Devices**: Devices connected to the network. Clients attached via repeater are marked with `via_device` pointing to the repeater.
* **Preserving Shared MACs**: Client devices only update registry entries exclusively owned by this integration, using `default_name` and `default_model` to avoid overwriting metadata from integrations like Sonos or Philips Hue.

### 4. Entity Platforms
* **Device Tracker (`device_tracker.py`)**: Presence tracking for connected devices with attributes (`node`, `access_point`, `band`, `ip_address`, `private_mac`).
* **Sensor (`sensor.py`)**:
  * Router metrics: connected devices, CPU usage, memory usage, last boot, last successful poll.
  * Total roams (`client_roams`) and per-client roam counters (`roams`).
  * Per-client Wi-Fi signal strength (dBm) and IP address sensors.
* **Binary Sensor (`binary_sensor.py`)**: Router reachability and connectivity status.
* **Event (`event.py`)**:
  * `RouterEventEntity`: Exposes router lifecycle events (`rebooted`) on the router device with triggering context preserved.
  * Note: Client roaming events are **not** attached to this entity; they are broadcast directly on the event bus to prevent duplicate logbook entries.

### 5. Logbook Integration (`logbook.py`)
* Implements `async_describe_events` to provide rich, human-readable entries:
  * `movistar_rft8115vw_client_roamed`: Formatted as `<Client Name> roamed from <Node A> to <Node B>`, linked directly to the client device's activity.
  * `movistar_rft8115vw_router_rebooted`: Formatted as `Movistar Askey Router rebooted`.

---

## Directory & File Structure

```
ha-movistar-askey/
├── custom_components/movistar_rft8115vw/
│   ├── __init__.py          # Entry setup, device registry initialization, platform forwarding
│   ├── binary_sensor.py     # Router connectivity binary sensor
│   ├── clients.py           # Client naming, MAC suffix deduplication, roam detection
│   ├── const.py             # Domain, bus events, configuration constants
│   ├── coordinator.py       # Polling coordinator, roaming detection, state synchronization
│   ├── device.py            # DeviceInfo builders (router, repeater, clients)
│   ├── device_tracker.py    # Scanner device tracker entities
│   ├── diag.py              # HA diagnostic dump support
│   ├── event.py             # Router event entity (reboot lifecycle)
│   ├── icons.json           # MDI icon assignments
│   ├── logbook.py           # HA Logbook describe_events integration
│   ├── manifest.json        # Integration metadata & version
│   ├── migration.py         # Config entry & unique ID migrations
│   ├── router.py            # HTTP client, session authentication, device table scraper
│   ├── sensor.py            # Router health, roam counters, client signal & IP sensors
│   ├── signal.py            # Client signal sensors enablement policy
│   ├── status.py            # Wi-Fi client details and system status parser
│   ├── strings.json         # Base localization strings
│   └── translations/        # English (en.json) and Spanish (es.json)
├── tests/                   # Pytest test suite
│   ├── test_clients.py
│   ├── test_coordinator_roams.py
│   ├── test_device.py
│   ├── test_diag.py
│   ├── test_event.py
│   ├── test_logbook.py
│   ├── test_migration.py
│   ├── test_router.py
│   ├── test_router_session.py
│   ├── test_signal.py
│   └── test_status.py
├── .github/workflows/
│   ├── validate.yaml        # CI: Ruff lint, Ruff format, Pytest, Hassfest, HACS
│   └── release.yaml         # Automatic GitHub release on push to main
├── CHANGELOG.md             # Keep a Changelog format
└── README.md                # Documentation and setup guide
```

---

## Development & Testing Commands

### Linting & Formatting (Ruff)

The project uses [Ruff](https://docs.astral.sh/ruff/) with an 88-character line limit.

```bash
# Check linting rules
ruff check .

# Check code formatting without modifying
ruff format . --check

# Apply formatting fixes automatically
ruff format .
ruff check --fix .
```

### Running Tests (Pytest)

Tests run with Python 3.14 (or Python 3.12+ with dependencies from `requirements.txt`):

```bash
# Run all tests
pytest

# Run a specific test module
pytest tests/test_event.py

# Run a single test function
pytest tests/test_event.py -k test_router_event_entity_types
```

---

## Git & Release Workflow

* **Branches**:
  * `dev`: Primary development branch. All feature work, bug fixes, and version preparations happen here.
  * `main`: Production/release branch. Only contains tagged release commits.
* **Automated Releases**:
  1. Bump `"version"` in `custom_components/movistar_rft8115vw/manifest.json`.
  2. Add a corresponding `## <version>` section at the top of `CHANGELOG.md`.
  3. Ensure all tests and `ruff` checks pass.
  4. Merge `dev` into `main` and push to `origin/main`.
  5. The `.github/workflows/release.yaml` action runs automatically:
     * Validates code (lint, test, hassfest, HACS).
     * Extracts release notes from `CHANGELOG.md` for `## <version>`.
     * Creates the git tag `<version>`.
     * Publishes the GitHub release.
