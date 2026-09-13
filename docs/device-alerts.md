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
