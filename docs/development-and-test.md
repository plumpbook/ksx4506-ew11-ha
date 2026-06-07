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
| Test Home Assistant | Real integration smoke test against controlled HA instance | Deploy the branch, restart HA, inspect entities and packet diagnostics. |
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
4. Deploy to a test Home Assistant instance and restart it.
5. Verify the changed feature through the HA UI or diagnostics surface.
6. Push the release commit and tag.
7. Confirm GitHub Actions for CI, HACS, and Hassfest pass.

`tests/test_release_notes.py` enforces that the current manifest version and all
local `v*` release tags have matching release note sections.
