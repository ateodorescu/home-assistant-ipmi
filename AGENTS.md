# AGENTS.md

Guidance for AI agents working in this repository.

## Project

HACS custom integration for Home Assistant that monitors and controls IPMI-capable servers.

- Domain: `ipmi`
- Install path: `custom_components/ipmi/`
- Distributed via HACS (`hacs.json`); CI validates with hassfest, HACS Action, and unit tests

## Layout

```
custom_components/ipmi/
  __init__.py      # setup, config entry, coordinator, send_command service
  const.py         # domain constants, platforms, commands, sensor filter defaults
  util.py          # pure helpers (unique_id, sensor id, redaction, kg key, auth heuristics)
  helpers.py       # typed hass.data accessors + device info helper
  server.py        # IpmiServer + IpmiDeviceInfo (connection / polling)
  config_flow.py   # UI config + options + zeroconf + reconfigure/reauth
  sensor.py        # sensors (state + backend + dynamic temp/fan/voltage/power/…)
  binary_sensor.py # chassis power binary sensor
  button.py        # power command buttons
  switch.py        # power on / soft shutdown switch
  diagnostics.py   # download diagnostics (redacted)
  device_action.py # device actions for power commands
  services.yaml    # send_command service schema
  strings.json     # config flow / service strings (source of truth)
  translations/    # en, de, el, fr
  manifest.json    # integration metadata + python-ipmi requirement
tests/             # pure unit tests (no Home Assistant install required)
```

Do not add code outside `custom_components/ipmi/` unless the task is docs, CI, tests, or HACS metadata.

## Architecture

1. **Config entries** — one entry per unique **alias** (`unique_id`); options include scan interval and sensor filters. The same host may appear on multiple entries if aliases differ.
2. **`IpmiServer`** (`server.py`) — single connection/data owner per entry; tracks `last_backend` (`addon` / `rmcp` / `none`).
3. **`IpmiCoordinator`** (`__init__.py`) — polls via `DataUpdateCoordinator`; blocking IPMI I/O runs in the executor; starts reauth on clear auth failures.
4. **Platforms** — `sensor`, `binary_sensor`, `button`, and `switch` entities are coordinator-backed.
5. **Runtime sensors** — new sensors are announced with `IPMI_NEW_SENSOR_SIGNAL`; sensors subscribe via dispatchers stored under `hass.data[DOMAIN]`.
6. **Diagnostics** — `diagnostics.py` exposes redacted entry data, backend, and sensor key lists.

### Connection backends (prefer addon)

`IpmiServer.update()` honors **backend_preference** (options, default `auto`):

| Preference | Behavior |
|---|---|
| `auto` (default) | Addon / standalone HTTP first, then python-ipmi (RMCP). After repeated addon transport failures, briefly skip probing. |
| `addon` | Addon only (no RMCP fallback) |
| `rmcp` | python-ipmi only (skips addon probes) |

Addon HTTP uses **GET** (query params; supported by current addons). POST is only used after a successful probe.

| Capability | Addon / standalone | python-ipmi |
|---|---|---|
| Sensors (temp/fan/voltage) | yes | yes |
| Current / power / time | yes | when SDR type/units map |
| Chassis power commands | yes | yes |
| Custom `send_command` | yes only | no |
| Kg key (RMCP+) | yes | ignored (warning logged) |

When changing connection or auth behavior, keep addon-first fallback as the **default** (`auto`) and preserve both paths unless the task explicitly drops one.

## Compatibility rules

- **Never change** existing entity `unique_id` strings (`{entry_id}_{alias}_{key}` / switch form).
- **Never remove** State sensor, device actions, or `send_command` without an explicit breaking-change request.
- Config entry `data` / `options`: additive keys only; migrate with defaults matching prior behavior.
- Config entry `unique_id` is the alias (lowercase). Entity unique IDs stay entry-id-based.

## Conventions

- Prefer Home Assistant patterns already used here: `ConfigEntry`, `DataUpdateCoordinator`, `CoordinatorEntity`, device registry, config flow, `async_add_executor_job` for blocking calls.
- Put shared constants in `const.py`; pure logic in `util.py`; typed `hass.data` access in `helpers.py`.
- Keep config entry migrations in `async_migrate_entry` when adding stored fields.
- Update `strings.json` and matching files under `translations/` together for user-facing text.
- Bump `version` in `manifest.json` when shipping a release-worthy change.
- Log with `_LOGGER = logging.getLogger(__name__)`. Prefer debug for expected fallbacks; avoid logging passwords or kg keys.
- Match nearby style: `from __future__ import annotations`, existing naming (`IpmiServer`, `get_ipmi_server`), broad exception handling around remote IPMI (fragile hardware).

## Do / don't

**Do**

- Keep changes focused on the requested behavior.
- Run or respect hassfest/HACS/pytest expectations (`manifest.json`, translations, services, `tests/`).
- Preserve backward-compatible config entry data when possible (see existing migrations for addon interface, kg_key, privilege_level, entry unique_id).

**Don't**

- Commit secrets, live BMC credentials, or `.env` files.
- Introduce YAML-only setup as the primary path; config flow is the supported UX.
- Block the event loop with IPMI/HTTP calls — use the executor.
- Assume every BMC exposes the same sensors; sensor discovery is dynamic.
- Rewrite working addon↔RMCP dual-path logic without a clear need.
- Migrate/rewrite entity registry unique IDs as part of normal feature work.

## Useful references

- README: install options, entities, backends, and `send_command`
- Companion addon: https://github.com/ateodorescu/home-assistant-addons
- Library fallback: https://github.com/kontron/python-ipmi
