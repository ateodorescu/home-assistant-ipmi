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
| DCMI power reading (`dcmi power reading`) | yes | yes (best effort, only when the `power` sensor type is selected) |
| Chassis power commands | yes | yes |
| Custom `send_command` service | yes only | no |
| IPMI 2.0 (RMCP+) | yes (`lanplus`) | optional, see **IPMI protocol** below (default IPMI 1.5) |
| Kg key (RMCP+) | yes | with IPMI 2.0 only (ignored with a warning over IPMI 1.5) |
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
- **Scan interval while powered off** (seconds) — poll period while the server reports power off, for example to poll every 15 s while it runs and every 10 minutes while it is off (options only; 0 to 3600, default 0 = same as the scan interval, so nothing changes unless you set it; values below 10 count as 10). The integration switches back to the normal scan interval on the first poll that sees power on, and power buttons/switch trigger an immediate poll. A failed poll keeps the current interval. To control polling entirely from automations instead, turn off *Enable polling for updates* in the entry's system options and call `homeassistant.update_entity` on any IPMI entity.
- **Sensor types to discover** — which groups are created for *newly discovered* sensors (default: all)
- **Create energy sensors from power readings** — kWh sensors for the Energy dashboard (default: on; disable if you only want raw power)
- **Power switch off delay** (seconds) — after soft shutdown, keep the power switch off while the OS stops (default: 60; set to 0 to follow live BMC state immediately; does not affect the State sensor)
- **Minimal IPMI (power only)** — for BMCs with a limited command set (e.g. [Sipeed NanoKVM](https://wiki.sipeed.com/hardware/en/kvm/NanoKVM/ipmi.html)): skips FRU and sensor polling; power status, binary sensor, switch, and buttons only. Status polling uses python-ipmi (RMCP), not the addon full poll. Chassis commands still use the addon when available.
- **Connection backend preference** — `auto` (default: try addon first, then RMCP), `addon` (addon only), or `rmcp` (python-ipmi only; skips addon probes). Default matches historical behavior.
- **IPMI protocol (python-ipmi)** — the LAN protocol used when the integration talks to the BMC directly (no addon): `IPMI 1.5 (RMCP)` (default, same as previous versions) or `IPMI 2.0 (RMCP+)`. Advanced setup / reconfigure only. Does not affect the addon, which keeps using its own *ipmitool interface* and extra parameters.
- **Cipher suite (IPMI 2.0 only)** — `auto` (default: python-ipmi tries suite 17, then 3) or a fixed suite `1`, `2`, `3`, `15`, `16` or `17`. Ignored with IPMI 1.5. Advanced setup / reconfigure only.

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

Only **admin** users can call `send_command`, because it runs any ipmitool command with the stored BMC credentials. Calls from non-admin users (for example a dashboard button or a script run by a non-admin) fail with *Unauthorized*. Automations fired by triggers run without a user and are not affected ([#89](https://github.com/ateodorescu/home-assistant-ipmi/issues/89)).

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
- Default `native_protocol=rmcp` keeps the python-ipmi connection on IPMI 1.5, as in earlier versions; IPMI 2.0 is opt-in

## Troubleshooting

### python-ipmi: privilege errors or timeouts without the addon (e.g. ASRock Rack X470D4U)

Without the addon, the integration connects with python-ipmi over **IPMI 1.5** by default. Some BMCs only accept a user (especially a low-privilege `USER` account) over **IPMI 2.0 / RMCP+**, and IPMI 1.5 then fails with errors such as `CompletionCodeError` with `cc=0x86` (privilege limit) ([#100](https://github.com/ateodorescu/home-assistant-ipmi/issues/100)).

1. Open **Reconfigure** on the entry and tick **Configure advanced options**.
2. Set **IPMI protocol (python-ipmi)** to **IPMI 2.0 (RMCP+)**.
3. Leave **Cipher suite** on **auto** first. If the connection opens but requests then time out (`RetryError`), pick a fixed suite: **3** works on the ASRock Rack X470D4U, where the default negotiation picks suite 17 and then hangs.

If you use a **Kg key**, python-ipmi now uses it with IPMI 2.0. Suites 3 and 17 use AES encryption, which needs the `cryptography` package; it ships with Home Assistant.

### Addon: `sdr list full` / signal 11 (e.g. Intel M50CYP)

The integration does not run `ipmitool` itself. Sensor discovery via the addon uses the companion [ipmi-server](https://github.com/ateodorescu/home-assistant-addons) HTTP API, which historically called `ipmitool … sdr list full`. On some Intel M50CYP BMCs that command segfaults (signal 11), while per-type queries such as `sdr type Temperature` still work ([#96](https://github.com/ateodorescu/home-assistant-ipmi/issues/96)).

**Immediate workarounds**

1. In the BMC, enable **Channel 3 / cipher suite 3** under RMCP+ cipher suite configuration (reporter workaround), and set Extra params / `addon_extra_params` to `-C 3`.
2. Or set **Connection backend preference** to `rmcp` (or leave `auto` so the integration can fall back when the addon returns `success: false`).

**Proper fix** is in the addon: fall back to per-type `sdr type` queries when `sdr list full` fails (never query Memory). Narrowing **Sensor types to discover** alone does not avoid the crash on older addon builds, because those builds still run `sdr list full` and only filter the parsed JSON afterward.
