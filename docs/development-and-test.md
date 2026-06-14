# Development And Test Workflow

This project is easiest to validate with a real Home Assistant instance that can
reach the EW11 bridge. Local unit tests are still required, but they cannot prove
that live RS-485 timing, ACK behavior, or Home Assistant entity surfaces work on
real hardware.

## Layers

Use three deployment layers:

| Layer | Purpose | Expected action |
| --- | --- | --- |
| Local | Unit tests and static checks | Run pytest before deploying anywhere. |
| Test Home Assistant | Real integration smoke test against controlled HA instance | Start only for the test window, deploy the branch, inspect entities and packet diagnostics, then stop it. |
| Public release | HACS/GitHub release | Push only after local and test HA validation. |

Only one Home Assistant instance should connect to the same EW11 at a time.

## Local Checks

Run:

```bash
python -m compileall -q custom_components tests
python -m pytest -q
```

The public artifact tests intentionally scan tracked and untracked repository
files for private/local environment identifiers. Use documentation-only
addresses such as `192.0.2.10`, `198.51.100.10`, `203.0.113.10`, or
`ew11.example.invalid` in examples.

## Test Home Assistant Deployment

A test HA deployment should:

- run the same Home Assistant minimum version declared in `hacs.json` or newer
- mount or copy `custom_components/ksx4506_ew11` into `/config/custom_components/ksx4506_ew11`
- restart Home Assistant after code changes
- connect to EW11 only when the production HA integration is disabled or disconnected
- stay stopped by default when it can reach the same EW11 as production HA

## On-Demand Test HA Lifecycle

Keep the test Home Assistant instance stopped during normal operation. Start it
only when a real EW11 smoke test is needed, then stop it immediately after the
test window.

This avoids two Home Assistant instances competing for the same EW11 data stream
and makes connection-health logs easier to interpret.

Recommended lifecycle:

1. Confirm production impact is acceptable, or disable the production EW11 integration.
2. Start the test HA instance.
3. Deploy or redeploy the branch under test.
4. Run the smoke checks below.
5. Stop the test HA instance.
6. Re-enable or verify the production EW11 integration.

Environment-specific commands, hostnames, IP addresses, and filesystem paths
should stay in local-only notes or ignored files, not in public documentation.

Recommended smoke checks:

1. Add the EW11 integration through the UI.
2. Confirm `Unsupported Packets` and `Packet Capture` sensors exist on the EW11 hub device.
3. Trigger one known light action and confirm the HA light state changes.
4. Trigger one known outlet action and confirm switch/power state changes.
5. Trigger one thermostat action and confirm target temperature or heating state changes.
6. For `0x33`, confirm `Entrance Panel`, `Elevator Status`, and related binary sensors exist when packets are observed.

## Packet Capture During Field Tests

For focused packet observation:

1. Open the EW11 integration options.
2. Set `packet_capture_filter` to a narrow device id list, for example `33`.
3. Enable `packet_capture_enabled`.
4. Perform the action once.
5. Read `Packet Capture` attributes.
6. Disable `packet_capture_enabled`.

Avoid leaving broad packet capture enabled during normal operation.

## Release Checklist

Before creating a public release:

1. Update `custom_components/ksx4506_ew11/manifest.json` version.
2. Add a matching `## vX.Y.Z` section to `RELEASE_NOTES.md`.
3. Run `python -m pytest -q`.
4. Start the test Home Assistant instance for the validation window.
5. Deploy to the test Home Assistant instance and restart it.
6. Verify the changed feature through the HA UI or diagnostics surface.
7. Stop the test Home Assistant instance.
8. Push the release commit and tag.
9. Confirm GitHub Actions for CI, HACS, and Hassfest pass.

`tests/test_release_notes.py` enforces that the current manifest version and all
local `v*` release tags have matching release note sections.
