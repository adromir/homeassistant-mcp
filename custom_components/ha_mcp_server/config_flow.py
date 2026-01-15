"""Config flow for MCP Server integration."""
from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from .const import (
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
_LOGGER = logging.getLogger(__name__)
class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MCP Server."""
    VERSION = 1
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step where the user configures the LLM connection."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}