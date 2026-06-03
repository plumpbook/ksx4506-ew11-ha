from __future__ import annotations

import sys
import types


def install_homeassistant_stubs() -> None:
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    helpers = types.ModuleType("homeassistant.helpers")

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.helpers"] = helpers

    _install_binary_sensor()
    _install_climate()
    _install_config_entries()
    _install_const()
    _install_core()
    _install_diagnostics()
    _install_device_registry()
    _install_dispatcher()
    _install_entity_registry()
    _install_entity_platform()
    _install_fan()
    _install_light()
    _install_number()
    _install_sensor()
    _install_switch()
    _install_update_coordinator()
    _install_valve()
    _install_voluptuous()


def _install_binary_sensor() -> None:
    binary_sensor = types.ModuleType("homeassistant.components.binary_sensor")

    class BinarySensorDeviceClass:
        GAS = "gas"
        RUNNING = "running"

    class BinarySensorEntity:
        pass

    binary_sensor.BinarySensorDeviceClass = BinarySensorDeviceClass
    binary_sensor.BinarySensorEntity = BinarySensorEntity
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor


def _install_climate() -> None:
    climate = types.ModuleType("homeassistant.components.climate")

    class ClimateEntity:
        pass

    class ClimateEntityFeature:
        TARGET_TEMPERATURE = 1

    climate.ClimateEntity = ClimateEntity
    climate.ClimateEntityFeature = ClimateEntityFeature

    climate_const = types.ModuleType("homeassistant.components.climate.const")

    class HVACMode:
        OFF = "off"
        HEAT = "heat"

    class HVACAction:
        OFF = "off"
        IDLE = "idle"
        HEATING = "heating"

    climate_const.HVACAction = HVACAction
    climate_const.HVACMode = HVACMode

    sys.modules["homeassistant.components.climate"] = climate
    sys.modules["homeassistant.components.climate.const"] = climate_const


def _install_config_entries() -> None:
    config_entries = types.ModuleType("homeassistant.config_entries")

    class ConfigEntry:
        pass

    class _BaseFlow:
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

        async def async_set_unique_id(self, unique_id):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            return None

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    class ConfigFlow(_BaseFlow):
        pass

    class OptionsFlow(_BaseFlow):
        pass

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    sys.modules["homeassistant.config_entries"] = config_entries


def _install_const() -> None:
    const = types.ModuleType("homeassistant.const")

    class UnitOfEnergy:
        KILO_WATT_HOUR = "kWh"

    class UnitOfPower:
        WATT = "W"

    class UnitOfTemperature:
        CELSIUS = "C"

    const.UnitOfEnergy = UnitOfEnergy
    const.UnitOfPower = UnitOfPower
    const.UnitOfTemperature = UnitOfTemperature
    sys.modules["homeassistant.const"] = const


def _install_core() -> None:
    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:
        pass

    def callback(func):
        return func

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    sys.modules["homeassistant.core"] = core


def _install_diagnostics() -> None:
    diagnostics = types.ModuleType("homeassistant.components.diagnostics")

    def async_redact_data(data, to_redact):
        return {
            key: "**REDACTED**" if key in to_redact else value
            for key, value in data.items()
        }

    diagnostics.async_redact_data = async_redact_data
    sys.modules["homeassistant.components.diagnostics"] = diagnostics


def _install_device_registry() -> None:
    device_registry = types.ModuleType("homeassistant.helpers.device_registry")
    device_registry.async_get = lambda hass: hass.device_registry
    device_registry.async_entries_for_config_entry = (
        lambda registry, entry_id: [
            entry
            for entry in registry.entries
            if entry_id in entry.config_entries
        ]
    )
    sys.modules["homeassistant.helpers.device_registry"] = device_registry


def _install_dispatcher() -> None:
    dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_connect = lambda *args, **kwargs: None
    dispatcher.async_dispatcher_send = lambda *args, **kwargs: None
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher


def _install_entity_platform() -> None:
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform


def _install_fan() -> None:
    fan = types.ModuleType("homeassistant.components.fan")

    class FanEntity:
        pass

    fan.FanEntity = FanEntity
    sys.modules["homeassistant.components.fan"] = fan


def _install_light() -> None:
    light = types.ModuleType("homeassistant.components.light")

    class ColorMode:
        BRIGHTNESS = "brightness"
        ONOFF = "onoff"

    class LightEntity:
        pass

    light.ColorMode = ColorMode
    light.LightEntity = LightEntity
    sys.modules["homeassistant.components.light"] = light


def _install_number() -> None:
    number = types.ModuleType("homeassistant.components.number")

    class NumberDeviceClass:
        TEMPERATURE = "temperature"

    class NumberEntity:
        pass

    number.NumberDeviceClass = NumberDeviceClass
    number.NumberEntity = NumberEntity
    sys.modules["homeassistant.components.number"] = number


def _install_sensor() -> None:
    sensor = types.ModuleType("homeassistant.components.sensor")

    class SensorDeviceClass:
        ENERGY = "energy"
        POWER = "power"

    class SensorStateClass:
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    class SensorEntity:
        pass

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = SensorEntity
    sensor.SensorStateClass = SensorStateClass
    sys.modules["homeassistant.components.sensor"] = sensor


def _install_switch() -> None:
    switch = types.ModuleType("homeassistant.components.switch")

    class SwitchEntity:
        pass

    switch.SwitchEntity = SwitchEntity
    sys.modules["homeassistant.components.switch"] = switch


def _install_update_coordinator() -> None:
    update_coordinator = types.ModuleType("homeassistant.helpers.update_coordinator")

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

        def __class_getitem__(cls, item):
            return cls

    class DataUpdateCoordinator:
        def __init__(self, *args, **kwargs):
            pass

        def __class_getitem__(cls, item):
            return cls

    update_coordinator.CoordinatorEntity = CoordinatorEntity
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


def _install_valve() -> None:
    valve = types.ModuleType("homeassistant.components.valve")

    class ValveDeviceClass:
        GAS = "gas"

    class ValveEntityFeature:
        OPEN = 1
        CLOSE = 2
        SET_POSITION = 4
        STOP = 8

    class ValveEntity:
        pass

    valve.ValveDeviceClass = ValveDeviceClass
    valve.ValveEntity = ValveEntity
    valve.ValveEntityFeature = ValveEntityFeature
    sys.modules["homeassistant.components.valve"] = valve


def _install_voluptuous() -> None:
    voluptuous = types.ModuleType("voluptuous")

    class Invalid(Exception):
        pass

    class Schema:
        def __init__(self, schema):
            self.schema = schema

        def __call__(self, value):
            return value

    class Required:
        def __init__(self, key, *, default=None):
            self.key = key
            self.default = default

        def __hash__(self):
            return hash((self.key, self.default))

        def __eq__(self, other):
            return (
                isinstance(other, Required)
                and self.key == other.key
                and self.default == other.default
            )

    def All(*validators):
        def validate(value):
            for validator in validators:
                value = validator(value)
            return value

        return validate

    def Coerce(value_type):
        return value_type

    def Range(*, min=None, max=None):
        def validate(value):
            if min is not None and value < min:
                raise Invalid("value is too small")
            if max is not None and value > max:
                raise Invalid("value is too large")
            return value

        return validate

    def In(values):
        def validate(value):
            if value not in values:
                raise Invalid("value is not allowed")
            return value

        return validate

    voluptuous.All = All
    voluptuous.Coerce = Coerce
    voluptuous.In = In
    voluptuous.Invalid = Invalid
    voluptuous.Range = Range
    voluptuous.Required = Required
    voluptuous.Schema = Schema
    sys.modules["voluptuous"] = voluptuous


def _install_entity_registry() -> None:
    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = lambda hass: hass.entity_registry
    entity_registry.async_entries_for_config_entry = (
        lambda registry, entry_id: [
            entry
            for entry in registry.entries
            if entry.config_entry_id == entry_id
        ]
    )
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry
