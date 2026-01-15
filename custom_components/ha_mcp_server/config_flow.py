"""Config flow for MCP Server integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.network import get_url, NoURLAvailableError

from .const import (
    DOMAIN, 
    CONF_LLM_URL, 
    CONF_LLM_PROVIDER, 
    CONF_LLM_MODEL,
    PROVIDER_OLLAMA,
    PROVIDER_KOBOLD,
    PROVIDER_OPENAI,
    DEFAULT_LLM_URL,
    DEFAULT_LLM_MODEL
)

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MCP Server."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step where the user configures the LLM connection."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors = {}
        if user_input is not None:
            return self.async_create_entry(title="MCP Server", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LLM_URL, default=DEFAULT_LLM_URL): str,
                vol.Required(CONF_LLM_PROVIDER, default=PROVIDER_OLLAMA): vol.In([PROVIDER_OLLAMA, PROVIDER_KOBOLD, PROVIDER_OPENAI]),
                vol.Required(CONF_LLM_MODEL, default=DEFAULT_LLM_MODEL): str
            }),
            errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self.generated_config = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_ide_config(user_input)

    async def async_step_ide_config(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Generate IDE Configuration JSON."""
        
        errors = {}
        description_placeholders = {}

        if user_input is not None:
            # User submitted the form (Selection made or Token pasted)
            url_choice = user_input.get("url_choice")
            token = user_input.get("token", "<YOUR_LONG_LIVED_ACCESS_TOKEN>")
            
            # Re-fetch the chosen URL
            try:
                if url_choice == "internal":
                    ha_url = get_url(self.hass, allow_external=False, allow_internal=True)
                else:
                    ha_url = get_url(self.hass, allow_external=True, allow_internal=False)
            except NoURLAvailableError:
                ha_url = "http://homeassistant.local:8123" # Fallback
            
            # Construct the JSON
            import json
            config_json = {
                "mcpServers": {
                    "homeassistant": {
                        "command": "npx",
                        "args": [
                            "-y",
                            "@modelcontextprotocol/server-sse-client",
                            "--url",
                            f"{ha_url}/api/mcp/sse",
                            "--headers",
                            json.dumps({"Authorization": f"Bearer {token}"})
                        ]
                    }
                }
            }
            
            self.generated_config = json.dumps(config_json, indent=2)
            return await self.async_step_display_result()

        # Initial Form - Detect available URLs
        urls = {}
        try:
            int_url = get_url(self.hass, allow_external=False, allow_internal=True)
            urls["internal"] = f"Internal: {int_url}"
        except: pass
        
        try:
            ext_url = get_url(self.hass, allow_external=True, allow_internal=False)
            urls["external"] = f"External: {ext_url}"
        except: pass
        
        if not urls:
            urls["internal"] = "Default (Auto-detect)"
        
        return self.async_show_form(
            step_id="ide_config",
            data_schema=vol.Schema({
                vol.Required("url_choice", default="internal"): vol.In(urls),
                vol.Optional("token", description={"suggested_value": ""}): str
            }),
            description_placeholders=description_placeholders
        )

    async def async_step_display_result(self, user_input=None):
        if user_input is not None:
             return self.async_create_entry(title="", data={})
        
        return self.async_show_form(
            step_id="display_result",
            data_schema=vol.Schema({}),
            description_placeholders={"config_json": self.generated_config}
        )