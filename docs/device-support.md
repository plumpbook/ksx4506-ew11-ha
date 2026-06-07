# Device Support

This document describes the Home Assistant surface exposed by the current
integration. It is based on implemented decoder behavior plus observed packets
from one live installation.

## Summary

| Device ID | Family | Entity types | Control | Notes |
| --- | --- | --- | --- | --- |
| `0x0E` | Light | `light` | Yes | Group/status packets are expanded into channel lights. Control targets the individual sub id when known. |
| `0x12` | Gas valve | `valve`, `binary_sensor` | Close only | Open/toggle is not exposed. Leak and moving state are exposed when payloads contain those bits. |
| `0x30` | Integrated meter | `sensor` | No | Water, gas, electricity, hot water, and heat meters are exposed when observed. |
| `0x33` | Entrance panel | `sensor`, `binary_sensor` | No | Status bits and elevator call/arrival events are read-only. |
| `0x36` | Thermostat | `climate`, `switch` | Partial | Heating on/off and whole-degree target temperature are supported. |
| `0x39` | Outlet / standby cutoff | `switch`, `sensor`, `binary_sensor` | Yes | Outlet on/off, power, auto cut, cutoff threshold, under-threshold, and overload are exposed. |
| `0x40` | Common entrance | `sensor` | No | Shared entrance open control is not exposed. |
| `0x60` | Unknown sensor-like device | `sensor` | No | One-byte response is exposed as a raw value until semantics are identified. |

## `0x0E` Light

Supported behavior:

- `0x81` status responses update light entities.
- Group-style status payloads are expanded into per-channel lights.
- Individual control uses `0x41` and waits for either control ACK or matching status.
- Existing channel state is preserved when building grouped/channel control payloads.

Known limitation:

- Dimming is exposed only when the status byte marks the light as dimmable.

## `0x12` Gas Valve

Supported behavior:

- Close command only.
- `Gas Leak` and `Gas Valve Moving` binary sensors are exposed when the status payload includes those bits.

Safety policy:

- Open and toggle are not exposed.
- Guarded gas commands require the explicit `gas_unlock` option.

Known limitation:

- More real `0x12` status samples are needed before open/closed state can be considered fully validated across vendors.

## `0x30` Integrated Meter

Supported meter sub ids:

| Sub ID | Meter | Instant unit | Total unit |
| --- | --- | --- | --- |
| `0x01` | Water | `m3` | `m3` |
| `0x02` | Gas | `m3` | `m3` |
| `0x03` | Electricity | `W` | `kWh` |
| `0x04` | Hot water | `m3` | `m3` |
| `0x05` | Heat | `MW` | `MW` |
| `0x0F` | Whole meter packet | expanded | expanded |

The coordinator probes meter states at startup so meter entities can appear even
before a user manually opens a meter page.

## `0x33` Entrance Panel

Supported behavior:

- `Entrance Panel` sensor shows the latest status byte.
- Binary sensors expose:
  - `All Lights Off Active`
  - `Auxiliary Input Active`
  - `Elevator Call Active`
  - `Elevator Down Active`
- `Elevator Status` sensor exposes:
  - `idle`
  - `calling`
  - `arrived`
  - `unknown`

Event details:

- `0x43` payload `0x10` is treated as elevator call acknowledged.
- `0x43` payload `0x80` is treated as elevator arrived.
- `last_panel_event_seq` increments on repeated event packets.

Known limitation:

- Physical controls such as all-lights-off or elevator-call are not exposed as buttons yet.
- `arrived` is momentary and can return to `idle` when the next status packet arrives.

## `0x36` Thermostat

Supported behavior:

- Multi-zone group status is expanded into zone climate entities.
- Heating can be turned on/off through a `Heating` switch and through climate HVAC mode.
- Target temperature is controlled by the climate entity.

Current temperature policy:

- Target temperature uses whole-degree steps.
- Fractional target values are rejected by the packet builder.

Known limitation:

- Away, schedule, and hot-water bits can appear in attributes, but dedicated controls are not exposed yet.

## `0x39` Outlet / Standby Cutoff

Supported behavior:

- Group status packets such as `39-1F` and `39-9F` are expanded into physical outlets.
- Physical outlets use individual sub ids such as `39-11`, `39-12`, and `39-91`.
- Entities include:
  - outlet `switch`
  - `Power` sensor
  - `Cutoff Threshold` sensor
  - `Auto Cut` binary sensor
  - `Under Threshold` binary sensor
  - `Overload` binary sensor

Known limitation:

- Outlet packets currently expose instantaneous wattage and flags. No cumulative energy value has been identified in these packets.

## `0x40` Common Entrance

Supported behavior:

- Common entrance call/status/open-request-shaped packets are classified as `common_entrance`.
- A read-only `Common Entrance` sensor exposes decoded event fields.

Safety policy:

- Shared building entrance open control is not exposed.
- Any future open control must be disabled by default and guarded by an explicit option.

## `0x60` Unknown Sensor

Supported behavior:

- A one-byte response is exposed as a raw sensor value.

Known limitation:

- The physical meaning of the value is not identified yet.
