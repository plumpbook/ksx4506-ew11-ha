from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .config import effective_config
from .const import CONF_EXPOSE_PACKET_SAMPLES, CONF_HOST, DOMAIN
from .coordinator import Ksx4506Coordinator
from .ew11_health import ew11_health_report_from_coordinator
from .packet_quality import empty_packet_quality_report

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics data that can be attached to GitHub issues."""

    coordinator: Ksx4506Coordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    config = effective_config(entry)
    include_packet_samples = bool(config.get(CONF_EXPOSE_PACKET_SAMPLES, False))
    unsupported = (
        coordinator.registry.unsupported_packet_report(
            include_packet_samples=include_packet_samples,
        )
        if coordinator is not None
        else {
            "total_seen": 0,
            "unique_signatures": 0,
            "packet_samples_redacted": not include_packet_samples,
            "packets": [],
        }
    )

    diagnostics = {
        "config_entry": {
            "title": _redact_title(entry.title, entry.data.get(CONF_HOST)),
            "data": async_redact_data(config, TO_REDACT),
        },
        "known_devices": _known_device_summary(coordinator),
        "ew11_connection": async_redact_data(
            ew11_health_report_from_coordinator(coordinator),
            TO_REDACT,
        ),
        "packet_quality": _packet_quality_summary(
            coordinator,
            include_packet_samples=include_packet_samples,
        ),
        "unsupported_packets": unsupported,
        "report_url": "https://github.com/plumpbook/ksx4506-ew11-ha/issues/new?template=unsupported_packet.yml",
    }
    return _redact_host_occurrences(diagnostics, entry.data.get(CONF_HOST))


def _redact_title(title: str, host: Any) -> str:
    if not isinstance(host, str) or not host:
        return title
    return title.replace(host, "**REDACTED**")


def _redact_host_occurrences(value: Any, host: Any) -> Any:
    if not isinstance(host, str) or not host:
        return value
    if isinstance(value, str):
        return value.replace(host, "**REDACTED**")
    if isinstance(value, dict):
        return {
            key: _redact_host_occurrences(item, host)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_host_occurrences(item, host) for item in value]
    return value


def _known_device_summary(coordinator: Ksx4506Coordinator | None) -> list[dict[str, Any]]:
    if coordinator is None:
        return []

    return [
        {
            "key": dev.key,
            "device_id": f"0x{dev.addr:02X}",
            "sub_id": f"0x{dev.sub_id:02X}",
            "kind": dev.kind,
            "channel": dev.channel,
            "state_keys": sorted(dev.state),
        }
        for dev in sorted(coordinator.registry.devices.values(), key=lambda item: item.key)
    ]


def _packet_quality_summary(
    coordinator: Ksx4506Coordinator | None,
    *,
    include_packet_samples: bool,
) -> dict[str, Any]:
    if coordinator is None:
        return empty_packet_quality_report(
            include_packet_samples=include_packet_samples
        )
    return coordinator.packet_quality_report(
        include_packet_samples=include_packet_samples
    )
