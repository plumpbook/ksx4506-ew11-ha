# Observed Device Inventory

This inventory is based on live EW11/Home Assistant debug logs from one KS X
4506 installation. It intentionally records protocol shape only: device IDs,
sub IDs, command IDs, payload lengths, and current integration handling. It
does not map devices to rooms or physical locations.

Capture window:

- Source: captured Home Assistant debug logs
- Sample size: 623 decoded RX frames
- Date: 2026-05-23

## Summary

| Device ID | Likely family | Observed sub IDs | Observed commands | Current handling | Notes |
| --- | --- | --- | --- | --- | --- |
| `0x0E` | Lighting | `0x11`..`0x15` | `0x01`, `0x81` | `light` | Supported as channel lights. Group-style payload lengths vary by sub ID. |
| `0x12` | Gas valve | `0x01` | `0x0F` | close-only `valve` plus binary sensors | Current capture did not include a gas status response, so open/closed state still needs field validation. |
| `0x30` | Integrated metering | `0x03` | `0x01`, `0x81` | `sensor` | Electricity payload decodes to instant/total values. |
| `0x33` | Entrance panel / batch bridge | `0x01` | `0x01`, `0x81` | read-only `sensor` | Physical entrance panel has all-lights-off, elevator-call, and living-room-light-3 controls. Current code decodes status only and does not expose generic switch writes. |
| `0x36` | Thermostat | `0x1F` | `0x01`, `0x81` | `climate` | Group status payload includes multiple zone temperature pairs. |
| `0x39` | Outlet / standby-power cutoff | `0x1F`, `0x2F`, `0x3F`, `0x4F`, `0x5F`, `0x9F` | `0x01`, `0x81` | `switch` with attributes | Payloads decode as channel supply state and wattage. |
| `0x40` | Unknown, possibly fan/ventilation | `0x02`, `0x03` | `0x01`, `0x02`, `0x82` | diagnostic/unknown | Needs a dedicated decoder after more samples. |
| `0x60` | Unknown sensor-like device | `0x01` | `0x01`, `0x81` | `sensor` raw value | Request carries 3 data bytes; response carries 1 data byte. Semantics unknown. |

## Repeated Frame Shapes

| Device | Sub ID | Command | Payload length | Example raw frame |
| --- | --- | --- | --- | --- |
| `0x0E` | `0x11` | `0x01` | `0` | `f70e110100e900` |
| `0x0E` | `0x11` | `0x81` | `4` | `f70e118104000000006d08` |
| `0x0E` | `0x12` | `0x81` | `3` | `f70e1281030000006904` |
| `0x0E` | `0x13` | `0x81` | `2` | `f70e13810200006904` |
| `0x0E` | `0x14` | `0x81` | `2` | `f70e14810200006e0a` |
| `0x0E` | `0x15` | `0x81` | `2` | `f70e15810200006f0c` |
| `0x12` | `0x01` | `0x0F` | `0` | `f712010f00eb04` |
| `0x30` | `0x03` | `0x81` | `8` | `f7300381080000048600350502fd76` |
| `0x33` | `0x01` | `0x01` | `1` | `f73301010101c4f2` |
| `0x33` | `0x01` | `0x81` | `3` | `f73301810300040043f6` |
| `0x36` | `0x1F` | `0x81` | `15` | `f7361f810f001f000000161b161b161a161a161b4230` |
| `0x39` | `0x1F` | `0x81` | `7` | `f7391f8107001000791000250ba0` |
| `0x39` | `0x2F` | `0x81` | `7` | `f7392f8107001004281002430a82` |
| `0x39` | `0x3F` | `0x81` | `7` | `f7393f8107009000229000174292` |
| `0x39` | `0x4F` | `0x81` | `7` | `f7394f8107001000059000018330` |
| `0x39` | `0x5F` | `0x81` | `7` | `f7395f8107001006791004127e4a` |
| `0x39` | `0x9F` | `0x81` | `10` | `f7399f810a00100001100000100005ce5e` |
| `0x40` | `0x02` | `0x02` | `0` | `f740020200b7f2` |
| `0x40` | `0x02` | `0x82` | `2` | `f740028202000035f2` |
| `0x40` | `0x03` | `0x01` | `0` | `f740030100b5f0` |
| `0x60` | `0x01` | `0x01` | `3` | `f7600101030004891902` |
| `0x60` | `0x01` | `0x81` | `1` | `f7600181010016f0` |

## Implementation Implications

1. Lighting, outlet, thermostat, and electricity meter are the most mature
   decoders in the current integration.
2. Gas valve control should remain close-only. The integration needs a real
   `0x12` status response sample before showing a confident open/closed state.
3. Device `0x40` should be the next discovery target. It appears repeatedly,
   but current command IDs do not match the existing generic fan guess.
4. Device `0x60` should stay as a raw sensor until the `0x01` request payload
   and `0x81` one-byte response are identified.
5. Device `0x33` is an entrance panel family, not a generic switch. Current
   captures and external EzVille examples use payload shape `[error, status,
   reserved]`; observed idle status is `0x04`. The known physical controls at
   this installation are all-lights-off, elevator-call, and living-room-light-3.
   Control buttons should wait for dedicated press captures.

## `0x33` Entrance Panel Status Notes

Observed status response:

```text
F7 33 01 81 03 00 04 00 43 F6
```

The second payload byte is the only status byte seen so far. Current decoder
exposes these conservative fields:

| Status bit | Field | Confidence | Notes |
| --- | --- | --- | --- |
| `0x20` | `elevator_down_active` | medium | Matches EzVille elevator-call examples. |
| `0x10` | `elevator_up_active` | low | Present in the reference implementation, but not observed locally yet. |
| `0x04` | `batch_idle_marker` | medium | `0x04` appears in idle examples; all-lights-off examples clear this bit. |
| `0x02` | `auxiliary_input_active` | low | Reference labels this as outing; this installation may use the same slot for another entrance-side function such as living-room-light-3. Needs capture. |

## Next Capture Goals

- Trigger a gas valve status refresh and capture whether `0x12` returns
  `0x81` or another status command.
- Press the physical entrance panel controls one at a time and capture `0x33`
  responses for all-lights-off, elevator-call, and living-room-light-3.
- Observe `0x40` while changing the related physical device state.
- Observe `0x60` around events that may affect the sensor value.
- Capture outlet state while toggling one known outlet channel to verify
  channel-to-sub-ID mapping.
