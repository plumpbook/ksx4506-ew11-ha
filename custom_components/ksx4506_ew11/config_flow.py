from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries

from .const import (
    CONF_CHECKSUM,
    CONF_ETX,
    CONF_GAS_UNLOCK,
    CONF_HOST,
    CONF_PORT,
    CONF_RETRY,
    CONF_STX,
    CONF_TIMEOUT,
    DEFAULT_CHECKSUM,
    DEFAULT_ETX,
    DEFAULT_PORT,
    DEFAULT_RETRY,
    DEFAULT_STX,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


class Ksx4506ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=f"EW11 {user_input[CONF_HOST]}", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Required(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Required(CONF_RETRY, default=DEFAULT_RETRY): int,
                vol.Required(CONF_CHECKSUM, default=DEFAULT_CHECKSUM): vol.In(["sum8", "xor8"]),
                vol.Required(CONF_STX, default=DEFAULT_STX): str,
                vol.Required(CONF_ETX, default=DEFAULT_ETX): str,
                vol.Required(CONF_GAS_UNLOCK, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
