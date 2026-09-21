"""Entry-scoped discovery lifecycle; imports stay lazy for platform loading."""
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import Ksx4506Coordinator
    from .discovery_runtime import DiscoveryRuntime

DATA_KEY = f"{DOMAIN}_discovery"


async def async_prepare_discovery(hass: HomeAssistant, entry: ConfigEntry,
                                  coordinator: "Ksx4506Coordinator") -> None:
    from .discovery_runtime import DiscoveryRuntime
    runtime = DiscoveryRuntime(coordinator, entry.entry_id)
    await runtime.async_load()
    hass.data.setdefault(DATA_KEY, {})[entry.entry_id] = runtime
    _register_review_service(hass)


def start_discovery(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime: DiscoveryRuntime = hass.data[DATA_KEY][entry.entry_id]
    runtime.start()


async def async_stop_discovery(hass: HomeAssistant, entry: ConfigEntry) -> None:
    runtime: DiscoveryRuntime | None = hass.data.get(DATA_KEY, {}).get(entry.entry_id)
    if runtime is not None:
        await runtime.stop()
        hass.data[DATA_KEY].pop(entry.entry_id, None)


def _register_review_service(hass: HomeAssistant) -> None:
    import voluptuous as vol
    from homeassistant.core import ServiceCall
    from homeassistant.exceptions import ServiceValidationError
    if hass.services.has_service(DOMAIN, "review_discovery"):
        return

    async def review(call: ServiceCall) -> None:
        runtime: DiscoveryRuntime | None = hass.data.get(DATA_KEY, {}).get(call.data["entry_id"])
        if runtime is None:
            raise ServiceValidationError("No discovery runtime for this entry")
        if not await runtime.async_review(call.data["endpoint"].upper(), call.data["approve"]):
            raise ServiceValidationError("No current discovery candidate for this entry and endpoint")

    hass.services.async_register(DOMAIN, "review_discovery", review, schema=vol.Schema({
        vol.Required("entry_id"): str,
        vol.Required("endpoint"): vol.All(str, vol.Match(r"^[0-9a-fA-F]{2}/[0-9a-fA-F]{2}$")),
        vol.Required("approve"): bool,
    }))
