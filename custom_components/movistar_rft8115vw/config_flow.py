"""UI configuration flow for the Movistar Askey Router integration."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CONSIDER_HOME,
    CONF_SCAN_INTERVAL,
    CONF_SIGNAL_SENSORS,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SIGNAL_SENSORS,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SIGNAL_SENSOR_MODES,
)
from .router import CannotConnectError, InvalidAuthError, MovistarAskeyClient


def _user_schema(values: dict[str, Any] | None = None) -> vol.Schema:
    values = values or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=values.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_PASSWORD, default=values.get(CONF_PASSWORD, "")): str,
        }
    )


def _seconds_selector(minimum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=MAX_SCAN_INTERVAL,
            step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): _seconds_selector(MIN_SCAN_INTERVAL),
        vol.Required(
            CONF_CONSIDER_HOME, default=DEFAULT_CONSIDER_HOME
        ): _seconds_selector(0),
        vol.Required(
            CONF_SIGNAL_SENSORS, default=DEFAULT_SIGNAL_SENSORS
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(SIGNAL_SENSOR_MODES),
                translation_key=CONF_SIGNAL_SENSORS,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

_NUMERIC_OPTIONS = (CONF_SCAN_INTERVAL, CONF_CONSIDER_HOME)


async def _async_validate(host: str, password: str) -> None:
    connector = aiohttp.TCPConnector(force_close=True)
    session = aiohttp.ClientSession(connector=connector)
    client = MovistarAskeyClient(session, host, password)
    try:
        await client.async_test_credentials()
    finally:
        await client.async_close()


class MovistarAskeyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the router and migrate legacy YAML."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for a configured router."""
        return MovistarAskeyOptionsFlow()

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle setup initiated from the Home Assistant UI."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                await _async_validate(host, user_input[CONF_PASSWORD])
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Movistar Askey Router ({host})",
                    data={CONF_HOST: host, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_CONSIDER_HOME: DEFAULT_CONSIDER_HOME,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_import(
        self,
        import_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Import settings from the deprecated YAML device tracker."""
        host = import_data[CONF_HOST].strip()
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Movistar Askey Router ({host})",
            data={CONF_HOST: host, CONF_PASSWORD: import_data[CONF_PASSWORD]},
            options={
                CONF_SCAN_INTERVAL: import_data.get(
                    CONF_SCAN_INTERVAL,
                    DEFAULT_SCAN_INTERVAL,
                ),
                CONF_CONSIDER_HOME: import_data.get(
                    CONF_CONSIDER_HOME,
                    DEFAULT_CONSIDER_HOME,
                ),
            },
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Change the router address or password of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                await _async_validate(host, user_input[CONF_PASSWORD])
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=host,
                    title=f"Movistar Askey Router ({host})",
                    data={CONF_HOST: host, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or {CONF_HOST: entry.data[CONF_HOST]}),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> config_entries.ConfigFlowResult:
        """Start reauthentication after credentials stop working."""
        self._reauth_entry_data = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Validate and store a replacement password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            entry = self._get_reauth_entry()
            try:
                await _async_validate(entry.data[CONF_HOST], user_input[CONF_PASSWORD])
            except CannotConnectError:
                errors["base"] = "cannot_connect"
            except InvalidAuthError:
                errors["base"] = "invalid_auth"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )


class MovistarAskeyOptionsFlow(config_entries.OptionsFlow):
    """Manage polling and presence options."""

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Display and store polling and presence options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    key: int(value) if key in _NUMERIC_OPTIONS else value
                    for key, value in user_input.items()
                }
            )
        schema = self.add_suggested_values_to_schema(
            OPTIONS_SCHEMA,
            {
                CONF_SCAN_INTERVAL: self.config_entry.options.get(
                    CONF_SCAN_INTERVAL,
                    DEFAULT_SCAN_INTERVAL,
                ),
                CONF_CONSIDER_HOME: self.config_entry.options.get(
                    CONF_CONSIDER_HOME,
                    DEFAULT_CONSIDER_HOME,
                ),
                CONF_SIGNAL_SENSORS: self.config_entry.options.get(
                    CONF_SIGNAL_SENSORS,
                    DEFAULT_SIGNAL_SENSORS,
                ),
            },
        )
        return self.async_show_form(step_id="init", data_schema=schema)
