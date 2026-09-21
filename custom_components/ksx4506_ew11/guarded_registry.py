"""Apply admission at the HA boundary, leaving protocol decoding independent."""
from .discovery import DeviceRegistry, DeviceState
from .discovery_guard import DiscoveryGuard, Observation


class GuardedRegistry(DeviceRegistry):
    def __init__(self, guard: DiscoveryGuard) -> None:
        super().__init__()
        self.guard = guard
        self._reviewed: set[str] = set()

    def upsert_from_frame(self, addr: int, sub_id: int, cmd: int,
                          payload: bytes, raw_hex: str) -> list[tuple[DeviceState, bool]]:
        # Preserve restored/registered devices; only proposals are held back.
        before_zones = {k: {z["channel"] for z in d.state.get("zones", [])}
                        for k, d in self.devices.items() if d.kind == "climate"}
        self.guard.evidence.observe(raw_hex)
        changes = self._upsert_from_frame(addr, sub_id, cmd, payload, raw_hex)
        new_keys = {d.key for d, is_new in changes if is_new}
        new_zones = {f"{d.key}_ch{z['channel']}" for d, is_new in changes
                     if not is_new and d.kind == "climate" for z in d.state.get("zones", [])
                     if z["channel"] not in before_zones.get(d.key, set())}
        endpoint = f"{addr:02X}/{sub_id:02X}"
        status = cmd == (0x82 if addr == 0x40 else 0x81)
        # Group-only replies do not independently identify physical channels.
        automatic = status and sub_id & 0x0F != 0x0F
        observation = Observation(endpoint, tuple(sorted(new_keys | new_zones)), raw_hex, automatic)
        if changes and (new_keys or new_zones or status):
            admitted = self.guard.observe(observation)
            if not admitted:
                for key in new_keys:
                    self.devices.pop(key, None)
                for device, is_new in changes:
                    if not is_new and device.kind == "climate":
                        device.state["zones"] = [z for z in device.state.get("zones", [])
                                                 if z["channel"] in before_zones.get(device.key, set())]
                changes = [(d, n) for d, n in changes if not n]
        candidates = self.cleanup_candidate_report()["candidates"]
        review_keys = {c["device_key"] for c in candidates}
        for key in review_keys - self._reviewed:
            self.guard.record(Observation(endpoint, (key,), raw_hex, False), "existing_device_review_only")
        self._reviewed = review_keys
        return changes
