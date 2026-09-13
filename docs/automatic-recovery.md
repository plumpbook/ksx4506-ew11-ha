# Automatic control recovery

Receive activity is not proof that an individual output changed. A failed
command is tracked separately for each controlled device/channel. It clears
only when the latest requested state is observed for that channel, or a new
command replaces that request. This is protocol-state confirmation, not an
independent measurement of the physical lamp or relay.

## Command recovery

- Supported light, switch, fan, and thermostat controls use the shared recovery
  path, including the thermostat target-temperature number entity.
- There are at most three command rounds, separated by 1 and 3 seconds. F7
  rounds use at most three sends and three confirmation queries each, honoring
  a lower configured `max_attempts`. A targeted state query precedes each retry
  so a delayed successful command need not be sent again.
- The entire request, including waiting for the bus, expires after 30 seconds.
- A new request for the same device/channel cancels the older pending request.
  Different channels remain independent. Heating mode and temperature controls
  for the same thermostat zone share a recovery key.
- Gas controls retain their existing safety guard and do not get additional
  recovery rounds. No new gas-open action is introduced.
- Pending controls are discarded during hub recovery, never replayed after a
  restart. New controls during that recovery window return an error; they are
  not silently queued for later.

## Hub monitoring, not automatic restart

The watchdog checks every 15 seconds and reports individual device failures in
one HA notification per integration entry. It never power-cycles the shared
wallpad or forces a hub reconnect. Native transport reconnection after a lost
connection and bounded command retries still apply. Continuous invalid bytes
cannot postpone the client's valid-frame receive deadline indefinitely.

See [device health alerts](device-alerts.md) for thresholds, exclusions, and
manual restart guidance. The previous `recovery_power_switch` option no longer
enables automatic cycling. Existing pending power-on journals are still honored
for the same configured target so an interrupted older cycle can restore power.
Do not use an EW11 outlet or a shared/safety-critical power circuit for a manual
wallpad restart. All connected controls may be interrupted during that restart.

## Monitoring

No additional diagnostic entities are created. Controlled entities expose
`control_status`, `recovery_attempts`, and `control_error`. The existing
**RS485 Device Vitality** sensor exposes `control_problems` and `recovery_state`;
an unresolved channel failure keeps its endpoint unresponsive even when sibling
channels report states. An HA persistent notification also identifies the
diagnostic surface to inspect. A receiving link must not hide that failure.

Local tests include real loopback TCP exchanges with a simulated wallpad. These
do not replace a controlled real-EW11 smoke test before a production release.
