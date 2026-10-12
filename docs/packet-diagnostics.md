# Packet Diagnostics

This integration deliberately separates unsupported packet reporting from device
creation. Unknown or unsafe packets should be visible to the user, but they
should not automatically become Home Assistant devices.

## Diagnostic Surfaces

### Connection and endpoint evidence

`EW11 Link` keeps its existing states and adds `link_summary`, `connection_epoch`,
and the cumulative `tx_write_attempts`. `receiving` means framing-valid traffic;
requests, ACKs, and other endpoints can keep it receiving while a particular
endpoint has no valid state reply.

`RS485 Device Vitality` now exposes `endpoint_summary` for registered endpoints,
including healthy records, and `state_check` for the last explicit check. Full
diagnostics and problem records additionally separate:

- `state_response_count`, `last_state_response_at`, and monotonic
  `seconds_since_state_response`: validated status replies.
- `command_ack_count` and `last_command_ack_at`: observed acknowledgement
  frames; these do not confirm the requested output state.
- `probe_failure_count`, `consecutive_probe_failures`, and the existing last
  probe result: status-query evidence.
- `invalid_response_count`: framing-valid response candidates rejected by the
  existing payload rules; vendor variants may still need investigation.
- `observation_state` and `status_summary`: unobserved, ACK-only, event-only,
  stale, or observed state. A restored identity with no valid state history
  stays unknown after query failures. A confirmed endpoint needs repeated
  query failures before becoming unresponsive; silence alone becomes stale.
- `last_state_connection_epoch` and `state_current_connection`: whether the
  stored state belongs to the current TCP connection. Reconnecting is not
  evidence that every endpoint has recovered.

Control entities retain `control_status` and add the requested channel/target,
request/finish times, `control_last_ack_at`, and `target_state_confirmed_at`.
An endpoint can have a valid current status while a requested channel remains
unconfirmed. Other channels or ACKs do not clear that failed target.

### Explicit state check

1. Open **Developer tools → Actions** and choose **KS X 4506 EW11: 상태 다시 확인**.
2. Select the integration entry and copy an endpoint from `endpoint_summary`,
   for example `0E/11` or `0x0E/0x11`. This is device ID / sub ID; a light
   channel such as `11-3` is not an endpoint.
3. Run the action once and inspect `state_check` or the action response. A
   confirmed result means a valid state frame was received, not that a physical
   lamp or relay was independently measured.

The action accepts only an active registered endpoint supported by the existing
status-query path. It sends no output command and cannot approve discovery.
It permits one actual write attempt, a two-second total deadline, one check per
entry at a time, a thirty-second endpoint cooldown and a five-second entry
cooldown. Checks are deferred while a user command is being processed. Queued work is cancelled on timeout,
cancel, or unload. A socket change during the check is reported separately.

`not_sent`, `transport_unconfirmed`, `no_response`, `busy`, `cooldown`,
`cancelled`, and `stopped` explain different outcomes. A failed write completion
may have transmitted bytes and is not proof that the device ignored a request.
Neither busy nor unsent checks create endpoint failure evidence.

The same distinction applies to background known-device and alert probes:
`last_query_result` records confirmed transmission versus unsent/uncertain
transport, response timeout, cancellation, and connection changes. Only an
exhausted query with confirmed transmission counts as a response failure.
An unsent alert probe still observes its scheduling interval without increasing
the endpoint failure count.

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

### Packet Quality

`Packet Quality` summarizes stream parsing and command retry health. Use it when
EW11 appears connected but devices are slow, unavailable, or intermittently fail
to respond.

Useful attributes:

- `state`: recent health state for the last 10 minutes
- `lifetime_state`: health state if all counters since integration start are
  considered
- `summary`: recent RX checksum/frame errors, F7 resync events, and control TX
  giveups, plus lifetime control/state-request giveups
- `recent`: recent 10-minute counts used to calculate `state`
- `rx.f7_checksum_errors`: F7 frames that had no recoverable valid next header
- `rx.f7_resync_events`: malformed F7 candidates where the decoder recovered at
  an embedded next F7 header
- `rx.stx_resync_events`: false STX candidates where the decoder recovered at a
  following valid header
- `rx.last_resync`: most recent resync reason and source frame
- `tx.giveups`: commands or state requests that exhausted confirmation attempts
- `tx.control_giveups`: user-facing control commands that exhausted
  ACK/status confirmation attempts
- `tx.state_request_giveups`: startup or follow-up state requests that exhausted
  status confirmation attempts
- `tx.last_giveup`: most recent command that was abandoned after retry attempts

Only recent RX errors and recent `tx.control_giveups` affect `state`. State
request giveups are kept in attributes for diagnosis, but they do not mark the
sensor unhealthy by themselves because restored historical entities may be
probed during startup.

Resync events are separated from checksum/frame errors because TCP/EW11 chunks
can contain a damaged or stale frame candidate immediately followed by a valid
frame, or a binary `0x02` byte that looks like STX inside an F7 stream. In those
cases the decoder should recover at the next valid header without reporting it
as a packet-quality failure.

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
