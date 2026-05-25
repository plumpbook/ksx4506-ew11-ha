from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DEVICE_ADDED
from .devices.entrance import ENTRANCE_PANEL_DEVICE_ID
from .devices.outlet import OUTLET_DEVICE_ID
from .entity_base import KsxEntity

_OUTLET_BINARY_STATE_KEYS = ("auto_cut", "under_threshold", "overload")
_SOURCE_SAME = object()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    added_keys: set[str] = set()

    def build_all():
        out = []
        for d in coordinator.registry.devices.values():
            out.extend(_binary_sensors_for_device(coordinator, d))
        return out

    init_ents = build_all()
    if init_ents:
        async_add_entities(init_ents)
        added_keys.update(e._attr_unique_id for e in init_ents)

    @callback
    def on_added(dev_key: str):
        d = coordinator.registry.devices.get(dev_key)
        if not d:
            return

        new_entities = []
        for ent in _binary_sensors_for_device(coordinator, d):
            if ent._attr_unique_id in added_keys:
                continue
            new_entities.append(ent)
            added_keys.add(ent._attr_unique_id)

        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_DEVICE_ADDED, on_added))


def _binary_sensors_for_device(coordinator, dev):
    out = []
    if dev.kind == "gas_valve":
        out.extend(_gas_binary_sensors(coordinator, dev))
    if dev.kind == "entrance_panel" and dev.addr == ENTRANCE_PANEL_DEVICE_ID:
        out.extend(_entrance_panel_binary_sensors(coordinator, dev))
    if dev.kind == "switch" and dev.addr == OUTLET_DEVICE_ID:
        out.extend(_outlet_binary_sensors(coordinator, dev))
    return out


def _gas_binary_sensors(coordinator, dev):
    return [
        KsxGasLeakSensor(coordinator, dev),
        KsxGasValveMovingSensor(coordinator, dev),
    ]


def _entrance_panel_binary_sensors(coordinator, dev):
    return [
        KsxStateBinarySensor(coordinator, dev, "all_lights_off_active", "All Lights Off Active"),
        KsxStateBinarySensor(coordinator, dev, "elevator_call_active", "Elevator Call Active"),
        KsxStateBinarySensor(coordinator, dev, "elevator_down_active", "Elevator Down Active"),
        KsxStateBinarySensor(coordinator, dev, "auxiliary_input_active", "Auxiliary Input Active"),
    ]


def _outlet_binary_sensors(coordinator, dev):
    out = []
    if "control_sub_id" in dev.state:
        return [
            KsxOutletBinarySensor(coordinator, dev, "auto_cut", "Auto Cut"),
            KsxOutletBinarySensor(coordinator, dev, "under_threshold", "Under Threshold"),
            KsxOutletBinarySensor(coordinator, dev, "overload", "Overload"),
        ]
    for channel, source_channel in _outlet_binary_display_channels(dev):
        out.extend(
            [
                KsxOutletChannelBinarySensor(
                    coordinator,
                    dev,
                    channel,
                    "auto_cut",
                    "Auto Cut",
                    source_channel=source_channel,
                ),
                KsxOutletChannelBinarySensor(
                    coordinator,
                    dev,
                    channel,
                    "under_threshold",
                    "Under Threshold",
                    source_channel=source_channel,
                ),
                KsxOutletChannelBinarySensor(
                    coordinator,
                    dev,
                    channel,
                    "overload",
                    "Overload",
                    source_channel=source_channel,
                ),
            ]
        )
    return out


def _outlet_binary_display_channels(dev):
    channels = []
    if any(key in dev.state for key in _OUTLET_BINARY_STATE_KEYS):
        channels.append((1, None))
    channels.extend(
        (channel["channel"] + 1, channel["channel"])
        for channel in dev.state.get("channels", [])
        if isinstance(channel, dict) and isinstance(channel.get("channel"), int)
    )
    return channels


class _KsxGasBinarySensor(KsxEntity, BinarySensorEntity):
    _state_key = ""

    def __init__(self, coordinator, dev) -> None:
        super().__init__(coordinator, dev)
        self._attr_unique_id = f"ksx4506_{self.dev_key}_{self._state_key}"

    @property
    def is_on(self) -> bool | None:
        if self._state_key not in self.dev.state:
            return None
        return bool(self.dev.state[self._state_key])


class KsxGasLeakSensor(_KsxGasBinarySensor):
    _attr_name = "Gas Leak"
    _attr_device_class = BinarySensorDeviceClass.GAS
    _state_key = "leak"


class KsxGasValveMovingSensor(_KsxGasBinarySensor):
    _attr_name = "Gas Valve Moving"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _state_key = "moving"


class KsxStateBinarySensor(KsxEntity, BinarySensorEntity):
    def __init__(self, coordinator, dev, state_key: str, name: str) -> None:
        super().__init__(coordinator, dev)
        self._state_key = state_key
        self._attr_name = name
        self._attr_unique_id = f"ksx4506_{self.dev_key}_{state_key}"

    @property
    def is_on(self) -> bool | None:
        if self._state_key not in self.dev.state:
            return None
        return bool(self.dev.state[self._state_key])


class KsxOutletBinarySensor(KsxStateBinarySensor):
    pass


class KsxOutletChannelBinarySensor(KsxEntity, BinarySensorEntity):
    def __init__(
        self,
        coordinator,
        dev,
        channel: int,
        state_key: str,
        name: str,
        *,
        source_channel=_SOURCE_SAME,
    ) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._source_channel = channel if source_channel is _SOURCE_SAME else source_channel
        self._state_key = state_key
        self._attr_name = name
        self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_{state_key}"
        self._set_ksx_device_info(
            device_key=f"{self.dev_key}_ch{channel}",
            name=f"KSX {self.addr:02X}-{self.sub_id:02X} ch{channel}",
        )

    @property
    def is_on(self) -> bool | None:
        if self._source_channel is None:
            if self._state_key not in self.dev.state:
                return None
            return bool(self.dev.state[self._state_key])

        channel = self._channel_state
        if channel is None or self._state_key not in channel:
            return None
        return bool(channel[self._state_key])

    @property
    def _channel_state(self):
        for channel in self.dev.state.get("channels", []):
            if channel.get("channel") == self._source_channel:
                return channel
        return None
