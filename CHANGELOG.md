# Changelog

## Unreleased

### Added

- Optional **IPMI 2.0 (RMCP+)** for the native python-ipmi connection, with a configurable **cipher suite** ([#100](https://github.com/ateodorescu/home-assistant-ipmi/issues/100)). Set under advanced setup / **Reconfigure**: *IPMI protocol (python-ipmi)* and *Cipher suite (IPMI 2.0 only)*. Fixes BMCs that reject IPMI 1.5 logins, such as the ASRock Rack X470D4U (use IPMI 2.0 with cipher suite 3)
- The **Kg key** is now used by python-ipmi when IPMI 2.0 is selected
- DCMI power readings on the python-ipmi (RMCP) path, for BMCs that only report power through `ipmitool dcmi power reading` and not as SDR sensors, such as Supermicro X11 ([#94](https://github.com/ateodorescu/home-assistant-ipmi/issues/94)). Installs without the addon (for example Docker) now get the same **Instantaneous power reading**, **Minimum/Maximum during sampling period** and **Average power reading over sample period** sensors (plus **Sampling period** when the `time` sensor type is selected) that the addon already provides, with the same entity keys, so energy sensors work too. The reading is best effort: it is only requested when the `power` sensor type is selected, errors never fail the poll, and BMCs that reject the command are not asked again until the integration reloads. SDR sensors with the same key take precedence, and the addon path is unchanged.
- **Scan interval while powered off** option (Configure) for a slower poll while the server is off ([#92](https://github.com/ateodorescu/home-assistant-ipmi/issues/92)). After each successful poll the integration picks the next interval from the chassis power state: the normal **Scan interval** while on (or unknown), the new interval while off. Default `0` means "same as the scan interval", so existing setups poll exactly as before. Diagnostics now also show both configured intervals

### Changed

- Requires `python-ipmi>=0.6.1` (first release with RMCP+ support)
- Config entry version 2.10: existing entries get `native_protocol=rmcp` (IPMI 1.5) and `native_cipher_suite=auto`, so nothing changes unless you opt in. The addon path is unaffected

## 1.22.3 — 2026-09-15

### Fixed

- Addon HTTP calls use a short connect timeout (5s) separate from the 60s read timeout, so an unreachable addon no longer blocks Home Assistant startup for up to ~60–120s before falling back to RMCP ([#91](https://github.com/ateodorescu/home-assistant-ipmi/pull/91))

## 1.22.2 — 2026-08-24

### Fixed

- Sensors that drop out of a poll (host powered off, BMC returning no readings) are no longer announced as new when they reappear, which re-created entities with existing unique IDs and logged `Platform ipmi does not generate unique IDs` on every power cycle ([#87](https://github.com/ateodorescu/home-assistant-ipmi/issues/87))
- Energy companion sensors are no longer re-announced on every poll: their keys are never part of reported SDR readings, so discovery tracking dropped them each cycle and could log the same duplicate unique ID warning

### Added

- Simplified Chinese translation (`zh-Hans`)

## 1.22.1 — 2026-08-17

### Fixed

- hassfest: missing commas in Greek/French translation JSON and `CONFIG_SCHEMA` for config-entry-only setup

### Changed

- GitHub Actions: checkout and setup-python updated to Node 24 runtimes

## 1.22.0 — 2026-08-13

### Added

- Optional **energy sensors** (kWh, `total_increasing`) derived from discovered power readings for use in the Home Assistant Energy dashboard ([#80](https://github.com/ateodorescu/home-assistant-ipmi/issues/80)); enabled by default under **Configure → Create energy sensors from power readings**
- **Power switch off delay** option ([#39](https://github.com/ateodorescu/home-assistant-ipmi/issues/39)): after soft shutdown, the power switch stays off for a configurable period (default 60 seconds) while the BMC may still report power on; set to 0 to disable; the State sensor is unchanged
- **Minimal IPMI (power only)** option ([#81](https://github.com/ateodorescu/home-assistant-ipmi/issues/81)) for BMCs with a limited command set (e.g. Sipeed NanoKVM): skips FRU/SDR polling; power status and chassis controls only
- Dynamic sensors expose **`ipmi_status`** (e.g. `ok`, `cr`) when provided by the ipmi-server addon; requires addon **2.5.4+** for failed/out-of-threshold readings such as **0 RPM | cr** ([#52](https://github.com/ateodorescu/home-assistant-ipmi/issues/52))

### Fixed

- Discover entities from the union of reported sensor metadata and readings so sensors with metadata but no numeric value still get created ([#52](https://github.com/ateodorescu/home-assistant-ipmi/issues/52))
- Chassis power commands (switch, buttons, device actions) are serialized with the RMCP session lock so polling and control no longer race ([#70](https://github.com/ateodorescu/home-assistant-ipmi/issues/70))
- Failed chassis commands raise visible errors instead of failing silently; successful commands log at info level
- Power switch **off delay** applies only after a successful soft shutdown, so a failed command no longer blocks retries via `switch.turn_off`

### Changed

- **Automations / scripts:** prefer **buttons** or **device actions** for power control; the power switch follows Home Assistant switch semantics (`turn_off` is skipped when the switch already reads off). See README.

## 1.21.3 — 2026-08-12

### Changed

- HACS packaging: releases attach `ipmi.zip` (`zip_release` + `filename` in `hacs.json`) so the store download counter works; GitHub Action uploads the asset on tag/release

## 1.21.2 — 2026-08-12

Reliability and connection UX improvements. **Backward compatible:** entity `unique_id`s, State sensor, device actions, and `send_command` are unchanged. Default backend behavior remains addon-first then RMCP (`backend_preference=auto`).

### Highlights

- Power commands fall back to RMCP when the addon returns `success: false` (not only when HTTP fails)
- Optional **backend preference** (`auto` / `addon` / `rmcp`) plus short addon cooldown after repeated failures
- Selecting **rmcp** shows a confirmation warning that `send_command` requires the addon
- RMCP session reuse; addon HTTP uses **GET** (POST only after a proven successful probe)
- Numeric sensors return `None` when a reading is missing (instead of the string `unknown`)
- Clearer `send_command` errors when the addon is unavailable / RMCP-only
- Shared device-info helper; broader unit tests

### Added

- Options / advanced: `backend_preference` (default `auto` = prior behavior)
- Config entry migration `2.5` for the new option default
- Diagnostics: backend preference, addon POST mode, entity unique_id scheme note
- Unit tests for RMCP sensor categorization, chassis fallback, addon GET/POST handling, backend preference

### Changed

- `IpmiServer` method names snake_cased (`get_from_addon`, …) with camelCase aliases kept
- Cached RMCP session closed on entry unload
- Device registry / entity device info use safe `.get` via shared helper
- `send_command` passes the ipmitool string as a request param (path no longer embeds `?params=`)
- Backend preference field descriptions note that `send_command` does not work with `rmcp`

### Compatibility

| Area | Behavior |
|------|----------|
| Entity `unique_id`s | Unchanged (`{entry_id}_{alias}_{key}`) |
| State sensor | Kept |
| Device actions | Kept |
| `send_command` | Addon path only (clearer error when unavailable; warn when choosing `rmcp`) |
| Addon → RMCP fallback | Preserved when `backend_preference=auto` (default) |
| Addon HTTP | GET (POST only after proven success) |

### Upgrade notes

- Reload or restart after updating so migration `2.5` and option defaults apply
- RMCP-only users can set **Connection backend preference** to `rmcp` to skip addon probes (`send_command` will not work in that mode)
- Entity unique IDs still change if you remove and re-add an entry (intentional BC; not migrated)

---

## 1.20.5 — 2026-08-12

Cumulative release of the BC-safe roadmap (phases 1–4) plus follow-up fixes since `1.17.0`. Existing entity unique IDs, the State sensor, device actions, and `send_command` are preserved.

### Highlights

- Power **buttons**, power **binary sensor**, redacted **diagnostics**, and **Connection backend** sensor
- **Reconfigure** and **reauth** flows
- Broader **RMCP** sensor mapping (current / power / time when SDR exposes them)
- **Sensor type** discovery filter (options + advanced setup)
- Stable config-entry **unique_id** from the **alias** (same host allowed with different aliases)
- Unit tests + pytest CI workflow

### Added

- `button` platform: power on / off / cycle / reset / soft shutdown
- `binary_sensor` platform: Power (State sensor kept)
- `diagnostics.py`: download diagnostics with password / Kg key redacted
- Connection backend diagnostic sensor (`addon` / `rmcp` / `none`), **enabled by default**
- Config flow: advanced step, reconfigure, reauthentication
- Options / advanced: scan interval + **sensor types to discover**
- `util.py` pure helpers and `tests/` (no Home Assistant install required)
- GitHub Actions workflow for unit tests
- README and `AGENTS.md` updates (backends matrix, entities, uniqueness)

### Changed

- Addon HTTP calls use explicit timeouts; coordinator uses `asyncio.timeout`
- Switch refreshes coordinator after power actions (no optimistic inventing of on/off)
- Dispatcher unsubscribers cleaned up on unload
- `async_setup` registers `send_command` via the executor
- Safer logging (credentials / Kg key redacted from connection errors)
- Config UX: basic step + optional advanced (addon, Kg key, privilege, sensor filters)
- RMCP maps current (sensor type) and power/time via IPMI unit codes where possible
- Multi-select sensor filters normalize a single selection stored as a string
- Config entry `unique_id` is the lowercase **alias** (not `host:port`)

### Removed / dropped

- Option to mark SDR sensor groups as diagnostic entity category (unused / confusing)
  - Stale `diagnostic_sensor_types` option is cleared on setup
- Dead code and unsafe password debug dumps from earlier internals cleanup

### Fixed

- Switch / coordinator state after power commands
- RMCP target / socket handling and safer connection close
- Sensor `native_value` returns `None` when states are missing (instead of a boolean)
- Duplicate detection no longer blocks a second entry on the same BMC host when the alias differs

### Upgrade notes

- Reload or restart after updating so migrations and options defaults apply
- Config entries migrate toward alias-based `unique_id` (entity IDs unchanged)
- **Connection backend** appears under the device’s diagnostic entities and should be enabled
- Removing and re-adding an entry still creates new entity unique IDs (history may not carry over)
- Sensor type filters affect **newly discovered** sensors only; existing entities stay

### Compatibility

| Area | Behavior |
|------|----------|
| Entity `unique_id`s | Unchanged scheme |
| State sensor | Kept |
| Device actions | Kept |
| `send_command` | Addon path only (unchanged) |
| Addon → RMCP fallback | Preserved |

---

## Earlier tagged baseline

### 1.17.0

Previous public tag before this roadmap landed in tree as `1.18`–`1.20.5` work.
