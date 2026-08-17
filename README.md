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

[![GitHub downloads](https://img.shields.io/github/downloads/ateodorescu/home-assistant-ipmi/total)](https://github.com/ateodorescu/home-assistant-ipmi/releases)
[![HA installs](https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=installs&query=$.ipmi.total&url=https://analytics.home-assistant.io/custom_integrations.json)](https://analytics.home-assistant.io)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ateodorescu&repository=home-assistant-ipmi&category=integration)

Install via [HACS](https://hacs.xyz) (button above), or copy the `custom_components` folder into your Home Assistant `config` folder.
Restart Home Assistant, then add the **IPMI** integration.

## Entities and controls

Each configured server (unique alias + BMC host/port) can expose:

**Sensors**

- **State** — textual on/off power state (kept for backward compatibility)
- Dynamic SDR sensors: temperature, fan, voltage, power, current, time (discovery depends on the BMC and backend; not marked diagnostic)
- Fan and other numeric sensors include an **`ipmi_status`** attribute when using the ipmi-server addon **2.5.4+** (e.g. `cr` for critical, `ok` for healthy) so failed fans such as **0 RPM | cr** are exposed and can be automated
- Optional **energy** companions (kWh, `total_increasing`) for discovered power sensors — see [Energy dashboard](#energy-dashboard)
- **Connection backend** — diagnostic entity (`addon` / `rmcp` / `none`), enabled by default

**Binary sensor**

- **Power** — `binary_sensor` with device class power (same signal as State; State sensor is not removed)

**Switch**

- Power on / soft shutdown — UI-friendly toggle; see [Power control in automations](#power-control-in-automations)

**Buttons**

- Power on, power off, power cycle, power reset, soft shutdown — **recommended for scripts and automations** (always execute; no switch state gate)

**Device actions**

- The same power commands remain available as device actions for existing automations

### Options

Integration options (Configure) and advanced setup / reconfigure:

- **Scan interval** (seconds) — coordinator poll period (options only)
- **Sensor types to discover** — which groups are created for *newly discovered* sensors (default: all)
- **Create energy sensors from power readings** — kWh sensors for the Energy dashboard (default: on; disable if you only want raw power)
- **Power switch off delay** (seconds) — after soft shutdown, keep the power switch off while the OS stops (default: 60; set to 0 to follow live BMC state immediately; does not affect the State sensor)
- **Minimal IPMI (power only)** — for BMCs with a limited command set (e.g. [Sipeed NanoKVM](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/ipmi.html)): skips FRU and sensor polling; power status, binary sensor, switch, and buttons only. Status polling uses python-ipmi (RMCP), not the addon full poll. Chassis commands still use the addon when available.
- **Connection backend preference** — `auto` (default: try addon first, then RMCP), `addon` (addon only), or `rmcp` (python-ipmi only; skips addon probes). Default matches historical behavior.

During initial setup or reconfigure, enable **Configure advanced options** to set sensor filters, energy sensors, minimal IPMI, and backend preference. The same settings remain editable later under **Configure**.
Changing filters does not remove already created entities; enabling a type later can create new ones after reload.

### Reconfigure and reauthentication

- Use **Reconfigure** on the integration entry to update host, port, credentials, addon URL, Kg key, and related settings
- If authentication fails clearly, Home Assistant may prompt for **reauthentication** (username/password)

### Diagnostics

Download diagnostics from the device/integration page. Output is redacted (password and Kg key stripped) and includes backend, device info, and sensor key lists.

### Energy dashboard

Home Assistant's Energy dashboard needs **energy** sensors (kWh) with `state_class: total_increasing`, not instantaneous **power** (W). IPMI reports power only; the integration does not invent BMC readings.

To track server or switch consumption:

1. Open **Configure** on the IPMI integration entry.
2. Enable **Create energy sensors from power readings**.
3. Reload the integration (options save triggers a reload automatically).

Each discovered power sensor gets a companion `{name} energy` entity (kWh) when **power** is included in **Sensor types to discover** and **Create energy sensors from power readings** is enabled (both on by default). Energy entities become unavailable (and stop accumulating) if power is excluded from sensor types, the energy option is turned off, or the linked power sensor entity is disabled in Home Assistant.

Alternatively, you can add Home Assistant's **Riemann sum integral** helper on any power entity yourself — disable the option above if you prefer helpers only.

### `send_command` service

Sends a custom ipmitool-style command through the addon HTTP API only (not available on RMCP-only connections). Placeholders `$host$`, `$port$`, `$username$`, and `$password$` are substituted. If the addon is unreachable or backend preference is `rmcp`, the service returns a clear error (or an empty message when *Ignore errors* is enabled).

The addon API uses GET with query parameters. POST is only used if it has already proven to return a successful payload (current addon builds ignore JSON bodies).

### Power control in automations

For scripts and automations, prefer **buttons** (`button.press`) or **device actions** over `switch.turn_on` / `switch.turn_off`:

| Control | Service | Notes |
|---|---|---|
| Soft shutdown | `button.press` on **Soft shutdown** | Always sends the command |
| Power on | `button.press` on **Power on** | Always sends the command |
| Legacy toggle | `switch.turn_on` / `switch.turn_off` | Home Assistant skips the call when the switch already reads on/off |

The power switch can read **off** for up to **Power switch off delay** seconds after a successful soft shutdown while the BMC still reports power on. During that window, `switch.turn_off` is ignored (switch already off). A failed soft shutdown no longer starts that delay, so you can retry immediately.

Chassis commands log at **info** (`Sending chassis command …` / `succeeded via addon|RMCP`). On failure, the service raises an error you can see in the automation trace. For deeper diagnosis:

```yaml
logger:
  logs:
    custom_components.ipmi: debug
```

Use the **Power** binary sensor or **State** sensor for conditions (`on` / `off`), not the switch state, after re-adding an entry (update stale entity IDs in scripts).

## Identity and uniqueness

- Config entries use a stable `unique_id` from the **alias** (lowercase) for duplicate detection — the same BMC host may be added more than once with different aliases
- Entity `unique_id`s remain based on the config entry id + alias + sensor key
- **Removing and re-adding** an entry creates a new config entry id, so entity unique IDs change and history/automations tied to those entity IDs may need updating

## Compatibility notes

- Do not rely on entity unique IDs surviving a remove/re-add (scheme stays `{entry_id}_{alias}_{key}` for backward compatibility; it is **not** migrated to alias-only IDs)
- State sensor, device actions, and the `send_command` service are kept for backward compatibility alongside buttons and the power binary sensor
- Default `backend_preference=auto` preserves addon-first then RMCP fallback
