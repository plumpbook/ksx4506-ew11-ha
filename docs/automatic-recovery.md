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

## Hub recovery

The watchdog checks every 15 seconds. A failing link or at least two independent
failing protocol endpoints must persist for 30 seconds before a TCP reconnect.
Multiple channels at one address count as **one** endpoint. Reconnection has a
five-minute cooldown. Continuous invalid bytes cannot postpone the client's
valid-frame receive deadline indefinitely; partial parser bytes are discarded
when a new TCP connection is established.

After reconnect, a bounded sweep queries known devices without changing outputs.
Power recovery is considered only after another 120 seconds, with no recent
device responses and a completed sweep of at least two targets returning no
responses. A disconnected bridge/network alone is insufficient for power cycling.

## Optional dedicated power switch

The integration option `recovery_power_switch` is empty by default. To opt in,
enter the entity ID of a **dedicated wallpad/bridge power switch**, for example
`switch.wallpad_power`. It must use another integration, be available, and
already be on. Do not use a shared circuit, a safety-critical appliance's power
switch, or an EW11-controlled outlet.

Power is turned off for five seconds, then restored. There is at most one attempt
per incident and one per 24 hours. The attempt is saved before sending power-off;
the cooldown survives HA reloads/restarts. An interrupted cycle retains a pending
power-on record and attempts restoration when the same configured target is
loaded again. Changing/removing that option after an interrupted cycle requires
manually checking power; the integration will not operate a different target.

These limits cannot fix a failed relay, wiring fault, protocol mismatch, or an
unreachable power switch. A failed restoration remains pending and requires
operator attention; no software can guarantee power restoration through a broken
network.

## Monitoring

No additional diagnostic entities are created. Controlled entities expose
`control_status`, `recovery_attempts`, and `control_error`. The existing
**RS485 Device Vitality** sensor exposes `control_problems` and `recovery_state`;
an unresolved channel failure keeps its endpoint unresponsive even when sibling
channels report states. An HA persistent notification also identifies the
diagnostic surface to inspect. A receiving link must not hide that failure.

Local tests include real loopback TCP exchanges with a simulated wallpad. These
do not replace a controlled real-EW11 smoke test before a production release.
