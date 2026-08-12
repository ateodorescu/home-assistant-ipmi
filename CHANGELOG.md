# Changelog

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
