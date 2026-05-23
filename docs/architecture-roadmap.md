# HA-Suroup Architecture And Roadmap

## Goal

HA-Suroup aims to let Home Assistant users control KS X 4506-compatible in-home devices through an EW11 RS-485 serial server.

The long-term target is a public GitHub repository that other residents can install without needing to understand the bus protocol, checksums, polling timing, or EW11 byte-stream behavior.

## Working Model

EW11 is the transport bridge. It should provide a TCP socket that carries raw serial bytes between Home Assistant and the RS-485 line.

KS X 4506 is the actual application protocol. The integration must not assume that one TCP packet is one KS X 4506 frame. TCP may split or merge bytes, so frame parsing must be stream-based.

The protocol stack should be separated like this:

```text
Home Assistant entities
Home Assistant coordinator/config entry
Device models and command catalog
KS X 4506 frame codec
EW11 TCP transport
RS-485 bus
KS X 4506 devices
```

## KS X 4506 Constraints

The common frame is:

```text
HEADER DEVICE_ID DEVICE_SUB_ID COMMAND_TYPE LENGTH DATA... XOR_SUM ADD_SUM
```

Core implementation requirements:

- `HEADER` is `0xF7`.
- Total frame length is `LENGTH + 7`.
- `XOR_SUM` is calculated over bytes from `HEADER` through the last `DATA` byte.
- `ADD_SUM` is the low byte of the sum from `HEADER` through `XOR_SUM`.
- Command direction is encoded in bit 7 of `COMMAND_TYPE`.
- Polling is master-driven; devices should only answer after a request.
- Requests must be serialized because the RS-485 bus is shared.
- Whole/group commands that have no ACK must be repeated three times where the device-specific standard says so.

## Recommended Home Assistant Shape

The first public version is a custom integration under:

```text
custom_components/ksx4506_ew11/
```

Recommended integration characteristics:

- `integration_type`: `hub`
- `iot_class`: `local_push`
- UI setup through `config_flow.py`
- TCP host/port and polling options stored in config entry data/options
- Korean and English translation files under `translations/`
- A single coordinator owning the EW11 connection, polling loop, command queue, and device state
- Entity platforms added as device support becomes stable: `light`, `cover`, `lock`, `valve`, `switch`, `sensor`, `climate`, `fan`, and possibly diagnostics entities

The protocol library can start inside the custom integration for speed. If it becomes useful beyond Home Assistant, split it later into a standalone Python package such as `suroup-ksx4506`.

## Device Support Order

Phase 1 should focus on low-risk protocol plumbing and compact device models:

1. Frame codec and checksum tests
2. EW11 TCP transport with reconnect and raw hex logging
3. Lighting: Home Assistant `light`
4. Gas valve: close-only Home Assistant `valve` plus leak/moving binary sensors
5. Door lock: likely `lock` or read-only status first, depending on real-world safety policy
6. Curtain: Home Assistant `cover`
7. Outlet: Home Assistant `switch` and sensors

Phase 2 can add devices with richer state models:

- Boiler: `climate`, switches, and water/heating modes
- Thermostat: `climate`
- Indoor ventilation: `fan`
- System air conditioner: `climate`
- Integrated metering: `sensor`
- Entrance panel: read-only status first, then explicit buttons after capture validation

## Safety Defaults

Initial releases should be conservative:

- Prefer status polling and diagnostics before enabling write commands.
- Gate risky commands, especially door lock and gas valve actions, behind explicit options.
- Model gas valves as close-only controls: expose open/closed status, do not expose open/toggle commands.
- Keep a raw frame trace available for debugging.
- Treat command ACK as separate from confirmed physical state.
- Mark entities unavailable when EW11 reconnect is in progress or polling fails repeatedly.

## Suggested Repository Layout

```text
custom_components/ksx4506_ew11/
  __init__.py
  manifest.json
  config_flow.py
  const.py
  coordinator.py
  ew11_client.py
  protocol.py
  frame.py
  devices/
    __init__.py
    lighting.py
    gas.py
    door_lock.py
  translations/
    en.json
    ko.json
tests/
  test_protocol.py
  test_ha_frame.py
  test_discovery.py
docs/
  architecture-roadmap.md
  observed-device-inventory.md
```

## Next Implementation Slice

The next coding step should keep device-specific protocol logic out of Home Assistant entity classes:

1. Decode the observed `0x40` device family after collecting state-change captures.
2. Identify the observed `0x60` one-byte sensor response.
3. Capture a real `0x12` gas status response so the close-only valve can show a confident open/closed state.
4. Keep diagnostics visible for unknown frames and vendor-specific variants.

## Open Questions For Real Hardware

- EW11 TCP mode: raw TCP server/client mode, port, timeout, reconnect behavior, and serial settings.
- Whether the EW11 is connected in parallel with an existing wallpad or replacing the master.
- Which KS X 4506 devices are physically present at home and which `DEVICE_ID`/`DEVICE_SUB_ID` values answer.
- Whether the actual devices strictly follow KS X 4506 or use vendor-specific extensions.
- Whether writes should be enabled for safety-sensitive devices in the first public release.

## Current External References

- Home Assistant Developer Docs: Config Flow, `manifest.json`, integration quality scale, and custom integration localization.
- HACS Docs: custom integration repository structure and publish requirements.
