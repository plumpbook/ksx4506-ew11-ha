# Discovery admission and local evidence

The HA entry installs a guarded registry before registry restoration and before
connecting to EW11. Protocol decoder tests still use the lower-level registry;
the production setup path always installs the admission gate. No AI, external
API, additional server, or additional diagnostic sensor is used.

## New identities

- A decoded new identity remains a candidate, not an HA device/entity.
- Automatic admission needs at least three observations spaced at least 60
  seconds apart, spanning at least 10 minutes, plus two matching state-query
  observations. The latest successful query must be within 10 minutes.
- The proposed set of device/channel keys must remain consistent. Changing or
  disappearing topology resets the proof, including any user approval.
- Group-address replies alone cannot prove individual physical channel identity;
  these and non-status discoveries require review rather than automatic admission.
- Candidate queries are read-only status requests: at most two candidates per
  minute, at least 10 minutes between attempts per endpoint, one attempt per
  query, and a two-second deadline. No on/off, temperature, valve, or power-cycle
  commands are sent. A busy command lock causes probing to defer.
- Registration pauses while the link is not receiving, recent packet quality is
  not `ok`, or evidence persistence has failed. Receiving/matching a frame is not
  proof of physical command success. Protocols without transaction identifiers
  provide time-window/address matching, not cryptographic request correlation.
- An unverified candidate expires after 24 hours and its endpoint is held for a
  further 24 hours. Existing devices at that endpoint continue receiving updates.
  There are at most 100 candidates and 100 holds. This discards proposals, **not
  Home Assistant registry entries**. Capacity overflow fails closed.

## Existing registered devices

Existing devices and restored thermostat zones are protected. Temporary silence,
query failures, or a smaller reported channel count never delete them. Newly
appearing thermostat zones are checked even inside an existing group.

Startup no longer invokes the previous destructive legacy-registry pruning pass.
Its old migration helpers remain available internally but are not run by setup.
Topology-shrink candidates and unlabeled/unassigned registered identities are
shown as review-only. Missing labels do not imply a fake device or absence of
automation/dashboard references. Labeled devices can still appear in topology
review; they remain protected.

**This version does not automatically delete any already-registered HA device.**
It automatically rejects/expires pre-registration candidates and flags existing
uncertain identities. Safe permanent deletion of historical registry entries
still needs positive invalid/duplicate evidence, current dependency checks,
a recoverable backup, and an explicitly reviewed deletion scope. None of those
requirements is replaced by a timeout count.

## Evidence

The per-entry HA Store key is
`ksx4506_ew11.<entry_id>.discovery_evidence` (storage schema 1, policy revision 1).
It holds up to 256 decision/query/error events, retained for at most 30 days.
Each event contains the timestamp, endpoint, proposed keys, decision, bounded raw
hex and up to four preceding/recent decoded frame samples. Raw hex is capped at
1024 characters per sample. Recent decoder checksum/frame error samples are also
copied into the journal by the maintenance tick; this is not a lossless recording
of every malformed byte. A busy bus can evict old events before the age limit.

Evidence is independent of the optional Packet Capture setting. Ordinary traffic
stays in a four-frame RAM ring rather than being logged continuously. HA Store
persists changed evidence in batches at roughly 60-second intervals, on review
actions, and on clean unload. Abrupt power loss can lose the latest unsaved batch.
Writes use HA's private, atomic storage option. During normal operation the saved
file is read back before resuming admission, because HA may only log write errors.
HA owns the final write during shutdown; admission remains paused then.
Normal diagnostics redact raw hex/context; the existing expose-packet-samples
option permits explicit export. Raw local evidence may reveal household activity;
do not publish it without review.

On restart, evidence and holds are restored but partial validation/approval
progress is intentionally reset; old observations never auto-admit a device.
Malformed or unsupported saved evidence fails setup closed instead of silently
overwriting the file. Current HA registries remain the source of existing-device
protection, even after evidence retention expires.

## Reviewing a new candidate

One grouped persistent notification reports pending and existing review items.
Each existing review item shows its current HA name/area and a **device detail**
shortcut. The full existing review list is included, not just the first 20.
Links are resolved within the current integration entry, refreshed after renames,
moves or removals on the normal maintenance tick, and never perform deletion or
control. Unregistered candidates and missing device records have no device link.
Download integration diagnostics and inspect `discovery_guard`:
`candidates`, `registered_review`, `evidence`, and `blocked_until`.

Use the HA action `ksx4506_ew11.review_discovery`:

```yaml
action: ksx4506_ew11.review_discovery
data:
  entry_id: YOUR_EW11_ENTRY_ID
  endpoint: "0E/1F"
  approve: true
```

Approve only after identifying the actual new circuit/device. Approval is scoped
to the currently observed key set and still requires fresh, spaced observations
and a healthy link. `approve: false` discards that candidate and holds the endpoint
for 24 hours. Approving an already-held endpoint clears the hold but starts fresh
verification; it does not restore previous approval or query success.
The action never deletes registered devices.

## Verification and rollout

Run unit tests, the isolated installed-HA/TCP loopback scenario, full repository
pytest, type checking, compilation and public-artifact checks. The loopback uses
no physical bridge and tests storage, notifications, services and read-only probes.
It does not establish live RS485 timing or physical device correctness. Follow
`development-and-test.md` for controlled NAS and HACS production rollout; only one
HA instance may connect to a real EW11.
