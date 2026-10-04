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
connection and bounded command retries still apply.

## TCP recovery and partial frames

- A closed connection, failed connection attempt or failed write reconnects the
  socket. Consecutive failures wait 1, 2, 4, 8, 16, 32 and then at most 60 seconds
  between attempts. Merely accepting TCP and closing it again does not reset this
  backoff. An established connection that has received valid frames and lasted
  at least two minutes resets it on the next failure.
- Silence alone never closes a socket. After at least 120 seconds without a valid
  frame, recovery additionally requires discarded input, an expired fragment, or at least
  three exhausted state-query requests since the last valid receive. One-way
  commands do not count as failed response requests. This preserves quiet links
  while allowing noise or unanswered queries to trigger socket recovery.
  A pending fragment defers this decision during its 30-second assembly window;
  a partial TCP read is never itself fault evidence. Confirmed assembly expiry
  cannot be deferred again by a stream of new incomplete headers. Any valid frame
  clears the receive fault evidence.
- Stop and explicit reconnect share a lifecycle lock. A stop requested during
  reconnect cleanup prevents replacement tasks from starting. Unloading the
  integration stops recovery; it cannot silently restart the client.
- F7 and STX payloads may contain header bytes, including a complete nested frame.
  The parser waits for the declared outer length and verifies its checksum before
  interpreting those bytes. It never promotes an embedded payload frame during
  an idle read. An incomplete fragment expires after 30 seconds and is discarded
  in full, with an `assembly_timeout` packet-quality event. A damaged length can
  therefore lose buffered successors until the fragment completes or expires;
  this conservative tradeoff prevents ambiguous data from becoming device state.

These operations reconnect the TCP stream only. They do not reboot EW11 hardware
or restart Home Assistant. An automated hardware reboot needs a documented
interface verified for the installed EW11 model and firmware. No guessed web
endpoint, Telnet command or extra reboot packet is used.

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
Connection diagnostics also report the current reconnect delay, consecutive
connection failures, failed response requests since valid receive, and the
evidence used to distinguish silence from a transport fault.

Local tests include real loopback TCP exchanges with a simulated wallpad. These
do not replace a controlled real-EW11 smoke test before a production release.
