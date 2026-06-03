from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_CHECKSUM,
    CONF_ETX,
    CONF_EXPOSE_PACKET_SAMPLES,
    CONF_GAS_UNLOCK,
    CONF_HOST,
    CONF_MAX_ATTEMPTS,
    CONF_PORT,
    CONF_RETRY,
    CONF_STX,
    CONF_TIMEOUT,
    DEFAULT_CHECKSUM,
    DEFAULT_ETX,
    DEFAULT_EXPOSE_PACKET_SAMPLES,
    DEFAULT_MAX_ATTEMPTS,
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


class Ksx4506ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
