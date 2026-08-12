# Changelog

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
