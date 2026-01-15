"""The MCP Server integration entry point."""
from __future__ import annotations
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN
from .mcp_api import HA_MCPServer, MCP_SSE_View, MCP_Message_View
_LOGGER = logging.getLogger(__name__)
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MCP Server from a config entry data (configured via UI)."""
    
    # Pass the entry data (URL, Provider, Model) to the runtime
    mcp_runtime = HA_MCPServer(hass, entry.data)
    
    # Register HTTP views for SSE and messages
    sse_view = MCP_SSE_View(mcp_runtime)
    hass.http.register_view(sse_view)
    hass.http.register_view(MCP_Message_View(sse_view.sse_transport))
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = mcp_runtime
    
    _LOGGER.info("MCP Ultimate Server v2.5 started with provider: %s", entry.data.get("llm_provider"))
    return True
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the MCP Server integration."""
    if entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id)
    return True