# Device health alerts and manual restart

## UX contract

Monitor every known EW11 endpoint, not one room. Reuse the existing diagnostic
sensor and one persistent HA notification per hub. A receiving TCP link never
overrides an individual failed command or lost state response.

Healthy devices remain quiet. A previously responsive endpoint with sustained
silence is queried without changing outputs. Three failed confirmation queries
raise an alert. Never-seen registry remnants and event-only devices are not
treated as silent failures. Devices without a supported query are labelled as
stale observations, not proven control failures. Explicit failed user controls
are reported even when passive traffic from another channel continues.

The notification lists affected device names, areas, and reasons. It is updated
in place when membership changes; unchanged errors do not produce new alerts.
When the reported failures recover, the same notification becomes a recovery
notice. Removed/disabled devices are excluded, not described as recovered.
Baselines and unresolved notices survive HA reloads. A previous failed command
whose matcher was lost at restart requires a newly confirmed control result;
unrelated state traffic is insufficient. Dismissing an unchanged notice suppresses
it for that monitor session; a new incident or HA reload can present it again.

No watchdog action cycles wallpad power or restarts the hub. Ordinary transport
reconnection and bounded per-command retries remain separate. Restart is an
operator decision. The notification explains the disruption and links to the
integration's device list; it does not contain a power action or a restart service.
The user can inspect and operate their existing dedicated power switch manually.
Opening or dismissing a notification never operates a device.

An existing interrupted power-off journal can still restore power on startup;
this safety restoration is not permission to start another cycle. A power cycle
alone is not physical control success. A failed control stays reported until its
matching state is observed or a newer command succeeds.

## Verification contract

Test historical ghosts, startup grace, brief silence, persistent silence in
multiple kinds/rooms, independent channels, unsupported polling, recovery,
unchanged-notification suppression, HA reload, disabled/removed devices, notification
dismissal, and automatic-power safety even with a configured power switch.

Previously confirmed baselines do not expire into a false recovery. Removing or
disabling a device ends its monitoring eligibility.

After a three-minute startup grace, queryable devices need at least three observed
responses (or a persisted confirmed baseline), three minutes of silence, and three
failed confirmation queries at least 30 seconds apart. At most four endpoints are
queried each 15-second scan, with a two-second timeout per endpoint. Busy command
transactions take priority. Unsupported queries use a 15-minute stale-observation
notice. Event-only devices without state responses cannot be assessed by silence;
their health remains unverified rather than assumed healthy.

Development and isolated HA tests do not authorize a production release or a
live power cycle. Keep real-device interruptions separately approved.

## Shared communication inspection

The existing **EW11 Link** entity keeps its unique ID and transport state values.
Its attributes add `inspection_state`, `inspection_needed`, `inspection_summary`,
the reason, failure duration, recovery attempts and failed endpoint count. The
same per-entry HA notification displays "통신 복구 안 됨 · EW11·네트워크 점검 필요".
It gives manual EW11 restart guidance after checking power, network, cabling and
RS-485. It cannot establish that an EW11 hardware reboot is required.

Receive-age decisions use `seconds_since_valid_rx`, a monotonic elapsed time
across TCP connections. Reconnection alone never restarts that receive clock.
`last_rx_at` and the existing wall-clock age remain display metadata; moving the
system clock forward or backward does not create or clear shared-link evidence.

A new inspection notice requires a three-minute startup grace and either:

- At least three actual connection/transport failures without valid receive,
  continuing for three minutes, with at least two subsequent connection attempts.
  Accepting TCP without a valid frame does not erase this evidence.
- At least two independently addressed, previously responsive endpoints with
  three failed confirmation queries each under the existing alert policy, no
  valid frame in the past three minutes, and another three minutes of sustained
  shared failure including at least one subsequent connection attempt.

Quiet traffic, an event-only device, a single downstream address, a failed
control alone, and discarded/checksum/partial-frame input do not establish shared
transport failure. Parser/query-triggered reconnections are excluded from actual
transport-failure counts. No additional probes, reconnects or device commands
are introduced by this inspection policy. Individual device alerts still apply.

Valid receive clears shared-link inspection evidence; it does not clear unrelated
failed controls or prove physical device operation. Removing a shared-failure
condition or stopping monitoring is described separately from confirmed receive.
Reload grace never labels an old notice as recovered. Unchanged notices stay
quiet. Link-only notice updates use a five-minute cooldown, preserved across
reloads; sensor attributes remain current during that delay. Independent device
membership changes can still update the existing notice. Notification IDs are
stable per configuration entry. Legacy notices created with process-specific IDs
are not deleted automatically and can be dismissed manually after an approved update.

The actual coordinator stop/unload path publishes `stopped` with
`inspection_needed=False` and closes its own active notification after the
watchdog has saved unresolved evidence. Closing a notice is monitoring cleanup,
not a recovery verdict. Start/reload publishes `starting` immediately, before
the first monitor tick, and uses a fresh grace period. The saved unresolved
incident and cooldown are retained for later reassessment.
