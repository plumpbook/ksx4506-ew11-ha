from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower

from .device_metadata import format_device_name
from .entity_base import KsxEntity

_SOURCE_SAME = object()


class KsxOutletPowerSensor(KsxEntity, SensorEntity):
    _attr_name = "Power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator,
        dev,
        *,
        channel: int | None = None,
        source_channel=_SOURCE_SAME,
    ) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._source_channel = channel if source_channel is _SOURCE_SAME else source_channel
        if channel is None:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_power"
        else:
            self._attr_name = "Power"
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_power"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=format_device_name(
                    self.addr,
                    self.sub_id,
                    channel=channel,
                    state=dev.state,
                ),
            )

    @property
    def native_value(self):
        if self._channel is not None:
            if self._source_channel is None:
                return self.dev.state.get("power_w")
            channel = self._channel_state
            if channel is None:
                return None
            return channel.get("power_w")
        return self.dev.state.get("power_w")

    @property
    def extra_state_attributes(self):
        if self._channel is not None:
            if self._source_channel is None:
                return {
                    key: value
                    for key, value in self.dev.state.items()
                    if key in {"channel_count", "channels", "auto_cut", "under_threshold", "overload"}
                }
            channel = self._channel_state
            return dict(channel) if channel is not None else {}
        return {
            key: value
            for key, value in self.dev.state.items()
            if key in {"channel_count", "channels", "auto_cut", "under_threshold", "overload"}
        }

    @property
    def _channel_state(self):
        for channel in self.dev.state.get("channels", []):
            if channel.get("channel") == self._source_channel:
                return channel
        return None


class KsxOutletThresholdSensor(KsxEntity, SensorEntity):
    _attr_name = "Cutoff Threshold"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator,
        dev,
        *,
        channel: int | None = None,
        source_channel=_SOURCE_SAME,
    ) -> None:
        super().__init__(coordinator, dev)
        self._channel = channel
        self._source_channel = channel if source_channel is _SOURCE_SAME else source_channel
        if channel is None:
            self._attr_unique_id = f"ksx4506_{self.dev_key}_threshold"
        else:
            self._attr_name = "Cutoff Threshold"
            self._attr_unique_id = f"ksx4506_{self.dev_key}_ch{channel}_threshold"
            self._set_ksx_device_info(
                device_key=f"{self.dev_key}_ch{channel}",
                name=format_device_name(
                    self.addr,
                    self.sub_id,
                    channel=channel,
                    state=dev.state,
                ),
            )

    @property
    def native_value(self):
        if self._channel is not None:
            if self._source_channel is None:
                return self.dev.state.get("threshold_w")
            threshold = self._channel_threshold
            if threshold is None:
                return None
            return threshold.get("threshold_w")
        return self.dev.state.get("threshold_w")

    @property
    def extra_state_attributes(self):
        if self._channel is not None:
            if self._source_channel is None:
                return {
                    key: value
                    for key, value in self.dev.state.items()
                    if key in {"threshold_count", "thresholds"}
                }
            threshold = self._channel_threshold
            return dict(threshold) if threshold is not None else {}
        return {
            key: value
            for key, value in self.dev.state.items()
            if key in {"threshold_count", "thresholds"}
        }

    @property
    def _channel_threshold(self):
        for threshold in self.dev.state.get("thresholds", []):
            if threshold.get("channel") == self._source_channel:
                return threshold
        return None
