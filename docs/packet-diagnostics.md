# Packet Diagnostics

This integration deliberately separates unsupported packet reporting from device
creation. Unknown or unsafe packets should be visible to the user, but they
should not automatically become Home Assistant devices.

## Diagnostic Surfaces

### Unsupported Packets

`Unsupported Packets` is a cumulative diagnostic sensor. Its state is the number
of unique unsupported/candidate packet signatures, not the total packet count.
Use the attributes for details:

- `summary`: total unsupported/candidate counts and unique signature count
- `total_seen`: total observed unsupported plus candidate packets
- `unsupported_seen`: total unsupported packet observations
- `candidate_seen`: total candidate packet observations
- `latest_unsupported_signature`: most recent unsupported packet summary
- `latest_candidate_signature`: most recent candidate packet summary
- `top_unsupported_signatures`: most repeated unsupported packet summaries
- `top_candidate_signatures`: most repeated candidate packet summaries
- `unsupported_packets`: detailed unsupported records
- `candidate_packets`: detailed candidate records

Raw packet samples are hidden by default. Set `expose_packet_samples` to `true`
only when packet-level analysis is needed.

### Packet Capture

`Packet Capture` is a short-term capture sensor for a specific observation
session. It records recent received frames while `packet_capture_enabled` is
enabled.

Useful options:

- `packet_capture_enabled`: enables the capture buffer
- `packet_capture_filter`: device ids to capture, such as `33`, `33,40`, or `*`
- `packet_capture_limit`: number of recent frames to keep

Use this for focused field work:

1. Set `packet_capture_filter` to the smallest useful device id list.
2. Enable `packet_capture_enabled`.
3. Perform the wallpad/app action once.
4. Read `Packet Capture` attributes.
5. Disable `packet_capture_enabled`.

## Packet Classifications

| Classification | Meaning | Device creation |
| --- | --- | --- |
| `supported` | Device id, sub id, command, and payload are understood by the current decoder. | May update or create a supported entity. |
| `ignored_request` | Known periodic/request frame that should not create a device or warning. | No device. |
| `candidate` | Known device id, but sub id or payload is not confirmed enough to expose as an entity. | No device. Kept for analysis. |
| `unsupported` | Unsupported device id or unsupported command for a known device. | No device. Kept for analysis. |

Common reasons:

- `unsupported_device_id`: device id is not supported by the integration
- `unsupported_command`: device id is known, but command is not supported
- `unregistered_sub_id`: device id is known, but sub id is outside the accepted range
- `candidate_light_packet`: light packet shape did not match a safe known model
- `candidate_outlet_packet`: outlet packet shape did not match a safe known model
- `candidate_meter_packet`: meter packet shape did not match a safe known model
- `thermostat_individual_without_group_state`: thermostat individual response arrived before the corresponding group state was known

## Privacy

Default diagnostics redact raw packet samples and EW11 host values. Raw packet
samples can still reveal device layout and activity timing. Before posting a
public issue, remove:

- home address, building, line, floor, and unit details
- personal names and account names
- private IP addresses and remote access hostnames
- unrelated local paths or machine names

Use documentation-only examples such as `192.0.2.10` or
`ew11.example.invalid` when an address-shaped value is needed.
