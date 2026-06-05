from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback

from .config import effective_config
from .const import (
    CONF_CHECKSUM,
    CONF_ETX,
    CONF_EXPOSE_PACKET_SAMPLES,
    CONF_GAS_UNLOCK,
    CONF_HOST,
    CONF_MAX_ATTEMPTS,
    CONF_PACKET_CAPTURE_ENABLED,
    CONF_PACKET_CAPTURE_FILTER,
    CONF_PACKET_CAPTURE_LIMIT,
    CONF_PORT,
    CONF_RETRY,
    CONF_STX,
    CONF_TIMEOUT,
    DEFAULT_CHECKSUM,
    DEFAULT_ETX,
    DEFAULT_EXPOSE_PACKET_SAMPLES,
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_PACKET_CAPTURE_ENABLED,
    DEFAULT_PACKET_CAPTURE_FILTER,
    DEFAULT_PACKET_CAPTURE_LIMIT,
    DEFAULT_PORT,
    DEFAULT_RETRY,
    DEFAULT_STX,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


def _validate_hex_byte(value: str) -> str:
    if not isinstance(value, str):
        raise vol.Invalid("hex byte must be a string")

    cleaned = value.strip().replace("0x", "").replace("0X", "")
    if len(cleaned) != 2:
        raise vol.Invalid("hex byte must use exactly two hex digits")

    try:
        int(cleaned, 16)
    except ValueError as exc:
        raise vol.Invalid("hex byte must be valid hexadecimal") from exc

    return cleaned.upper()


def _validate_host(value: str) -> str:
    if not isinstance(value, str):
        raise vol.Invalid("host must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise vol.Invalid("host is required")
    return cleaned


def _validate_packet_capture_filter(value: str) -> str:
    if not isinstance(value, str):
        raise vol.Invalid("packet capture filter must be a string")

    cleaned = value.strip()
    if not cleaned or cleaned.lower() in {"*", "all"}:
        return cleaned

    for token in cleaned.replace(";", ",").replace(" ", ",").split(","):
        token = token.strip()
        if not token:
            continue
        token = token.removeprefix("0x").removeprefix("0X")
        try:
            device_id = int(token, 16)
        except ValueError as exc:
            raise vol.Invalid(
                "packet capture filter must contain hex device ids"
            ) from exc
        if device_id < 0 or device_id > 0xFF:
            raise vol.Invalid("packet capture device ids must fit in one byte")

    return cleaned


class Ksx4506ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return Ksx4506OptionsFlow(config_entry)

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"EW11 {user_input[CONF_HOST]}", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): _validate_host,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=65535),
                ),
                vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=0.1, max=30),
                ),
                vol.Required(CONF_RETRY, default=DEFAULT_RETRY): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=10),
                ),
                vol.Required(CONF_MAX_ATTEMPTS, default=DEFAULT_MAX_ATTEMPTS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=20),
                ),
                vol.Required(CONF_CHECKSUM, default=DEFAULT_CHECKSUM): vol.In(["sum8", "xor8"]),
                vol.Required(CONF_STX, default=DEFAULT_STX): _validate_hex_byte,
                vol.Required(CONF_ETX, default=DEFAULT_ETX): _validate_hex_byte,
                vol.Required(CONF_GAS_UNLOCK, default=False): bool,
                vol.Required(
                    CONF_EXPOSE_PACKET_SAMPLES,
                    default=DEFAULT_EXPOSE_PACKET_SAMPLES,
                ): bool,
                vol.Required(
                    CONF_PACKET_CAPTURE_ENABLED,
                    default=DEFAULT_PACKET_CAPTURE_ENABLED,
                ): bool,
                vol.Required(
                    CONF_PACKET_CAPTURE_FILTER,
                    default=DEFAULT_PACKET_CAPTURE_FILTER,
                ): _validate_packet_capture_filter,
                vol.Required(
                    CONF_PACKET_CAPTURE_LIMIT,
                    default=DEFAULT_PACKET_CAPTURE_LIMIT,
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=100),
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class Ksx4506OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        config = effective_config(self._config_entry)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TIMEOUT,
                    default=config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(
                    vol.Coerce(float),
                    vol.Range(min=0.1, max=30),
                ),
                vol.Required(
                    CONF_RETRY,
                    default=config.get(CONF_RETRY, DEFAULT_RETRY),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=10),
                ),
                vol.Required(
                    CONF_MAX_ATTEMPTS,
                    default=config.get(CONF_MAX_ATTEMPTS, DEFAULT_MAX_ATTEMPTS),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=20),
                ),
                vol.Required(
                    CONF_GAS_UNLOCK,
                    default=config.get(CONF_GAS_UNLOCK, False),
                ): bool,
                vol.Required(
                    CONF_EXPOSE_PACKET_SAMPLES,
                    default=config.get(
                        CONF_EXPOSE_PACKET_SAMPLES,
                        DEFAULT_EXPOSE_PACKET_SAMPLES,
                    ),
                ): bool,
                vol.Required(
                    CONF_PACKET_CAPTURE_ENABLED,
                    default=config.get(
                        CONF_PACKET_CAPTURE_ENABLED,
                        DEFAULT_PACKET_CAPTURE_ENABLED,
                    ),
                ): bool,
                vol.Required(
                    CONF_PACKET_CAPTURE_FILTER,
                    default=config.get(
                        CONF_PACKET_CAPTURE_FILTER,
                        DEFAULT_PACKET_CAPTURE_FILTER,
                    ),
                ): _validate_packet_capture_filter,
                vol.Required(
                    CONF_PACKET_CAPTURE_LIMIT,
                    default=config.get(
                        CONF_PACKET_CAPTURE_LIMIT,
                        DEFAULT_PACKET_CAPTURE_LIMIT,
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=1, max=100),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
