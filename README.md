# IPMI connector for Home Assistant

## What is IPMI?

IPMI (Intelligent Platform Management Interface) is a set of standardized specifications for
hardware-based platform management systems that makes it possible to control and monitor servers centrally.

## Home Assistant integration

This integration monitors and controls servers that support IPMI. It can connect in three ways:

- via the `ipmi-server` addon from [home-assistant-addons](https://github.com/ateodorescu/home-assistant-addons) (wrapper around `ipmitool`)
- via the `ipmi-server-standalone` Docker container:

  ```bash
  docker pull ghcr.io/ateodorescu/ipmi-server-standalone:latest
  ```

- via the Python library [python-ipmi](https://github.com/kontron/python-ipmi) (RMCP fallback)

If the addon / standalone HTTP API is reachable it is used first; otherwise the integration falls back to python-ipmi.

### Addon vs RMCP capabilities

| Capability | Addon / standalone | python-ipmi (RMCP) |
|---|---|---|
| Temperature / fan / voltage sensors | yes | yes |
| Current / power / time sensors | yes (when BMC exposes them) | yes when SDR type/units map (Amps / Watts / seconds) |
| Chassis power commands | yes | yes |
| Custom `send_command` service | yes only | no |
| Kg key (RMCP+) | yes | ignored (warning logged) |
| Connection backend diagnostic | shows `addon` | shows `rmcp` |

## Installation

Install via HACS or copy the `custom_components` folder into your Home Assistant `config` folder.
Restart Home Assistant, then add the **IPMI** integration.

## Entities and controls

Each configured server (unique alias + BMC host/port) can expose:

**Sensors**

- **State** — textual on/off power state (kept for backward compatibility)
- Dynamic SDR sensors: temperature, fan, voltage, power, current, time (discovery depends on the BMC and backend; not marked diagnostic)
- **Connection backend** — diagnostic entity (`addon` / `rmcp` / `none`), enabled by default

**Binary sensor**

- **Power** — `binary_sensor` with device class power (same signal as State; State sensor is not removed)

**Switch**

- Power on / soft shutdown

**Buttons**

- Power on, power off, power cycle, power reset, soft shutdown

**Device actions**

- The same power commands remain available as device actions for existing automations

### Options

Integration options (Configure) and advanced setup / reconfigure:

- **Scan interval** (seconds) — coordinator poll period (options only)
- **Sensor types to discover** — which groups are created for *newly discovered* sensors (default: all)
- **Connection backend preference** — `auto` (default: try addon first, then RMCP), `addon` (addon only), or `rmcp` (python-ipmi only; skips addon probes). Default matches historical behavior.

During initial setup or reconfigure, enable **Configure advanced options** to set sensor filters and backend preference. The same settings remain editable later under **Configure**.
Changing filters does not remove already created entities; enabling a type later can create new ones after reload.

### Reconfigure and reauthentication

- Use **Reconfigure** on the integration entry to update host, port, credentials, addon URL, Kg key, and related settings
- If authentication fails clearly, Home Assistant may prompt for **reauthentication** (username/password)

### Diagnostics

Download diagnostics from the device/integration page. Output is redacted (password and Kg key stripped) and includes backend, device info, and sensor key lists.

### `send_command` service

Sends a custom ipmitool-style command through the addon HTTP API only (not available on RMCP-only connections). Placeholders `$host$`, `$port$`, `$username$`, and `$password$` are substituted. If the addon is unreachable or backend preference is `rmcp`, the service returns a clear error (or an empty message when *Ignore errors* is enabled).

The addon API uses GET with query parameters. POST is only used if it has already proven to return a successful payload (current addon builds ignore JSON bodies).

## Identity and uniqueness

- Config entries use a stable `unique_id` from the **alias** (lowercase) for duplicate detection — the same BMC host may be added more than once with different aliases
- Entity `unique_id`s remain based on the config entry id + alias + sensor key
- **Removing and re-adding** an entry creates a new config entry id, so entity unique IDs change and history/automations tied to those entity IDs may need updating

## Compatibility notes

- Do not rely on entity unique IDs surviving a remove/re-add (scheme stays `{entry_id}_{alias}_{key}` for backward compatibility; it is **not** migrated to alias-only IDs)
- State sensor, device actions, and the `send_command` service are kept for backward compatibility alongside buttons and the power binary sensor
- Default `backend_preference=auto` preserves addon-first then RMCP fallback
