from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .devices.thermostat import (
    HEAT_CONTROL_REQUEST,
    STATE_RESPONSE_COMMANDS,
    STATUS_RESPONSE,
    TEMPERATURE_CONTROL_REQUEST,
    build_thermostat_heat_request,
    build_thermostat_temperature_request,
    decode_thermostat_state,
    thermostat_target_sub_id,
)
from .protocol import KsFrame


async def async_send_thermostat_heat_control(
    coordinator,
    *,
    addr: int,
    status_sub_id: int,
    channel: int | None,
    turn_on: bool,
) -> None:
    target_sub_id = thermostat_target_sub_id(status_sub_id, channel)
    frame = build_thermostat_heat_request(target_sub_id, turn_on=turn_on)

    response_matcher = _thermostat_heat_success_matcher(
        addr=addr,
        target_sub_id=target_sub_id,
        status_sub_id=status_sub_id,
        channel=channel,
        turn_on=turn_on,
    )
    matched = await coordinator.async_send_f7_command_and_confirm(
        addr,
        frame.sub_id,
        HEAT_CONTROL_REQUEST,
        frame.data,
        response_matcher,
        status_sub_id=status_sub_id,
        confirmation_matcher=_status_confirmation_matcher(
            response_matcher,
            status_sub_id=status_sub_id,
        ),
        interval=0.5,
        confirmation_interval=0.5,
    )
    if matched is None:
        raise HomeAssistantError("KSX thermostat heat state was not confirmed")


async def async_send_thermostat_temperature_control(
    coordinator,
    *,
    addr: int,
    status_sub_id: int,
    channel: int | None,
    temperature: float,
) -> None:
    target_sub_id = thermostat_target_sub_id(status_sub_id, channel)
    frame = build_thermostat_temperature_request(
        target_sub_id,
        temperature=temperature,
    )

    response_matcher = _thermostat_temperature_success_matcher(
        addr=addr,
        target_sub_id=target_sub_id,
        status_sub_id=status_sub_id,
        channel=channel,
        temperature=temperature,
    )
    matched = await coordinator.async_send_f7_command_and_confirm(
        addr,
        frame.sub_id,
        TEMPERATURE_CONTROL_REQUEST,
        frame.data,
        response_matcher,
        status_sub_id=status_sub_id,
        confirmation_matcher=_status_confirmation_matcher(
            response_matcher,
            status_sub_id=status_sub_id,
        ),
        interval=0.5,
        confirmation_interval=0.5,
    )
    if matched is None:
        raise HomeAssistantError(
            "KSX thermostat target temperature was not confirmed"
        )


def _thermostat_heat_success_matcher(
    *,
    addr: int,
    target_sub_id: int,
    status_sub_id: int,
    channel: int | None,
    turn_on: bool,
) -> Callable[[KsFrame], bool]:
    def matcher(frame: KsFrame) -> bool:
        if frame.addr != addr:
            return False
        if frame.sub_id not in {target_sub_id, status_sub_id}:
            return False
        if frame.cmd not in STATE_RESPONSE_COMMANDS:
            return False

        state = decode_thermostat_state(frame.payload, sub_id=target_sub_id)
        zones = state.get("zones", [])

        if channel is None:
            return _state_matches(state, turn_on)

        if frame.sub_id == target_sub_id and len(zones) == 1:
            return _state_matches(zones[0], turn_on)

        for zone in zones:
            if zone.get("channel") == channel:
                return _state_matches(zone, turn_on)

        return _state_matches(state, turn_on)

    return matcher


def _thermostat_temperature_success_matcher(
    *,
    addr: int,
    target_sub_id: int,
    status_sub_id: int,
    channel: int | None,
    temperature: float,
) -> Callable[[KsFrame], bool]:
    def matcher(frame: KsFrame) -> bool:
        if frame.addr != addr:
            return False
        if frame.sub_id not in {target_sub_id, status_sub_id}:
            return False
        if frame.cmd not in STATE_RESPONSE_COMMANDS:
            return False

        state = decode_thermostat_state(frame.payload, sub_id=target_sub_id)
        zones = state.get("zones", [])

        if channel is None:
            return _target_temperature_matches(state, temperature)

        if frame.sub_id == target_sub_id and len(zones) == 1:
            return _target_temperature_matches(zones[0], temperature)

        for zone in zones:
            if zone.get("channel") == channel:
                return _target_temperature_matches(zone, temperature)

        return _target_temperature_matches(state, temperature)

    return matcher


def _state_matches(state: Mapping[str, Any], turn_on: bool) -> bool:
    if "on" not in state:
        return False
    return bool(state["on"]) is turn_on


def _target_temperature_matches(
    state: Mapping[str, Any],
    temperature: float,
) -> bool:
    target_temp = state.get("target_temp")
    if target_temp is None:
        return False
    return abs(float(target_temp) - float(temperature)) < 0.01


def _status_confirmation_matcher(
    response_matcher: Callable[[KsFrame], bool],
    *,
    status_sub_id: int,
) -> Callable[[KsFrame], bool]:
    def matcher(frame: KsFrame) -> bool:
        return (
            frame.sub_id == status_sub_id
            and frame.cmd == STATUS_RESPONSE
            and response_matcher(frame)
        )

    return matcher
