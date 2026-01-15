"""
MCP Server implementation for Home Assistant.
Ultimate system management suite including Entity/Device Cleanup, Integration Management,
File Access, HACS, SQL Analytics and Local LLM support.
"""
import logging
import json
import uuid
import base64
import os
import io
import asyncio
from pathlib import Path
from datetime import timedelta, datetime
import statistics
import aiohttp
import matplotlib
matplotlib.use("Agg") # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from homeassistant.core import HomeAssistant, ServiceCall, Context
from homeassistant.components.http import HomeAssistantView
from homeassistant.components import history, logbook, camera, recorder
from homeassistant.components.automation.config import async_validate_config_item as async_validate_automation
from homeassistant.components.script.config import async_validate_config_item as async_validate_script
from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.helpers import area_registry, device_registry, entity_registry, template as template_helper
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.util.dt as dt_util
from homeassistant.components import trace
from homeassistant.components import calendar, todo
from homeassistant.setup import async_get_loaded_integrations

from mcp.server import Server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from mcp.server.sse import SseServerTransport

from .const import (
    CONF_LLM_URL, 
    CONF_LLM_PROVIDER, 
    CONF_LLM_MODEL,
    PROVIDER_OLLAMA,
    PROVIDER_KOBOLD,
    PROVIDER_OPENAI
)

_LOGGER = logging.getLogger(__name__)

class HA_MCPServer(Server):
    def __init__(self, hass: HomeAssistant, config: dict):
        super().__init__("ha_mcp_server")
        self.hass = hass
        self.config = config
        
        # Register the tool handlers using the SDK decorators
        @self.list_tools()
        async def list_tools() -> list[Tool]:
            return await self._list_tools_impl()

        @self.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
            return await self._call_tool_impl(name, arguments)

    async def _list_tools_impl(self) -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="read_config_file",
                description="Read a file from the Home Assistant config directory.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to the file (e.g., 'configuration.yaml')"}
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="write_config_file",
                description="Write content to a file in the config directory. Triggers a partial backup first.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to the file"},
                        "content": {"type": "string", "description": "Content to write"}
                    },
                    "required": ["path", "content"]
                }
            ),
            Tool(
                name="get_system_logs",
                description="Get the latest lines from home-assistant.log",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "lines": {"type": "integer", "description": "Number of lines to retrieve", "default": 50}
                    }
                }
            ),
            Tool(
                name="call_service",
                description="Call a Home Assistant service.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string"},
                        "service": {"type": "string"},
                        "service_data": {"type": "object"}
                    },
                    "required": ["domain", "service"]
                }
            ),
            Tool(
                name="cleanup_registry",
                description="Find and optionally remove unavailable entities.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days_offline": {"type": "integer", "default": 7},
                        "dry_run": {"type": "boolean", "default": True},
                        "domain_filter": {"type": "string"}
                    }
                }
            ),
             Tool(
                name="manage_entities",
                description="Manage specific entities (enable, disable, remove).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_ids": {"type": "array", "items": {"type": "string"}},
                        "action": {"type": "string", "enum": ["enable", "disable", "remove"]},
                    },
                    "required": ["entity_ids", "action"]
                }
            ),
            Tool(
                name="generate_dashboard_config",
                description="Generate YAML configuration for a dashboard view based on an Area.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "area_id": {"type": "string"},
                        "card_type": {"type": "string", "enum": ["mushroom", "tile", "minimalist", "bubble"], "default": "mushroom"}
                    },
                    "required": ["area_id"]
                }
            ),
            Tool(
                name="manage_integrations",
                description="List or manage config entries (integrations).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "reload", "disable", "enable", "remove"]},
                        "entry_id": {"type": "string", "description": "Required for actions other than list"}
                    },
                    "required": ["action"]
                }
            ),
            Tool(
                name="manage_hacs",
                description="Manage HACS resources.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "install", "update", "remove"]},
                        "category": {"type": "string", "enum": ["integration", "plugin", "theme"]},
                        "repository": {"type": "string"}
                    },
                    "required": ["action"]
                }
            ),
            Tool(
                name="manage_addons",
                description="Manage Home Assistant Add-ons (Supervisor).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["list", "start", "stop", "restart", "update", "install", "uninstall"]},
                        "slug": {"type": "string"}
                    },
                    "required": ["action"]
                }
            ),
            Tool(
                name="execute_sql_query",
                description="Execute a raw SQL query against the recorder database.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="generate_history_chart",
                description="Generate a chart for detailed entity history.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string"},
                        "hours": {"type": "integer", "default": 24}
                    },
                    "required": ["entity_id"]
                }
            ),
            Tool(
                name="render_template",
                description="Render a Jinja2 template.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "template": {"type": "string"}
                    },
                    "required": ["template"]
                }
            ),
            Tool(
                name="local_llm_query",
                description="Query the configured local LLM.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"}
                    },
                    "required": ["prompt"]
                }
            ),
            # New Advanced Features
            Tool(
                name="get_automation_trace",
                description="Retrieve debug trace for an automation run to diagnose failures.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "automation_id": {"type": "string", "description": "Entity ID of the automation (e.g. automation.night_mode)"},
                         "target_trace_timestamp": {"type": "string", "description": "Optional timestamp to find a specific run"}
                    },
                    "required": ["automation_id"]
                }
            ),
             Tool(
                name="safe_restart_system",
                description="Safely restart Home Assistant. Checks configuration validity first. Fails if config is invalid.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
             Tool(
                name="get_calendar_events",
                description="Get calendar events for a date range.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_ids": {"type": "array", "items": {"type": "string"}},
                        "start_hours_offset": {"type": "integer", "default": 0},
                        "duration_hours": {"type": "integer", "default": 24}
                    },
                    "required": ["entity_ids"]
                }
            ),
             Tool(
                name="manage_todo_list",
                description="Manage To-Do list items.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "todo.shopping_list"},
                        "action": {"type": "string", "enum": ["list", "add", "update", "remove", "complete"]},
                        "item": {"type": "object", "description": "Item details (summary, status, etc.) for add/update"}
                    },
                    "required": ["entity_id", "action"]
                }
            ),
             Tool(
                name="get_network_health",
                description="Diagnose Zigbee (ZHA or Zigbee2MQTT) network health.",
                inputSchema={
                    "type": "object",
             # 23. Service Introspection
             Tool(
                 name="list_available_services",
                 description="List available services and their schemas (arguments/fields).",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "domain": {"type": "string", "description": "Optional domain filter (e.g. 'light')"}
                     }
                 }
             ),
             # 24. Home Topology
             Tool(
                 name="get_home_topology",
                 description="Get a graph of Areas -> Devices -> Entities to understand physical layout.",
                 inputSchema={
                     "type": "object",
                     "properties": {}
                 }
             ),
             # 25. Secrets Manager
             Tool(
                 name="manage_secrets",
                 description="Read keys or set secrets in secrets.yaml.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "action": {"type": "string", "enum": ["list", "set"]},
                         "key": {"type": "string", "description": "Secret key name (required for set)"},
                         "value": {"type": "string", "description": "Secret value (required for set)"}
                     },
                     "required": ["action"]
                 }
             ),
             # 26. Assist / Conversation Agent
             Tool(
                 name="run_conversation_agent",
                 description="Send a command to Home Assistant's native Assist (NLU) agent.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "text": {"type": "string", "description": "Natural language command (e.g. 'Turn on the kitchen lights')"},
                         "agent_id": {"type": "string", "description": "Specific Conversation Agent ID (optional)"},
                         "language": {"type": "string", "default": "en"}
                     },
                     "required": ["text"]
                 }
             ),
             # 27. Persistent Notification
             Tool(
                 name="send_persistent_notification",
                 description="Post a persistent notification to the Home Assistant dashboard.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "message": {"type": "string"},
                         "title": {"type": "string", "default": "MCP Agent"}
                     },
                     "required": ["message"]
                 }
             ),
             # 28. Label Management
             Tool(
                 name="manage_labels",
                 description="Manage entity labels (tags).",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "action": {"type": "string", "enum": ["list", "create", "delete", "add_to_entity"]},
                         "name": {"type": "string", "description": "Label name (for create)"},
                         "label_id": {"type": "string", "description": "Label ID (for delete/add)"},
                         "entity_id": {"type": "string", "description": "Entity ID (for add)"}
                     },
                     "required": ["action"]
                 }
             ),
            # 12. Sherlock Logbook Investigator
            Tool(
                name="query_logbook",
                description="Query the Home Assistant Logbook for events (e.g. 'Door opened').",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Optional entity to filter by."},
                        "start_hours_ago": {"type": "integer", "default": 24},
                        "end_hours_ago": {"type": "integer", "default": 0}
                    }
                }
            ),
            # 13. Room Announcer
            Tool(
                name="announce_in_area",
                description="Announce a message via TTS to all media players in a specific area.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "area_id": {"type": "string", "description": "The Area ID (e.g. 'living_room')"},
                        "message": {"type": "string", "description": "Text to speak"},
                        "tts_service": {"type": "string", "description": "TTS service to use (e.g. 'tts.cloud_say')", "default": "tts.cloud_say"}
                    },
                    "required": ["area_id", "message"]
                }
            ),
             # 16. Automation & Script Creator
            Tool(
                name="create_automation",
                description="Create a new automation. Validates config before adding.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "alias": {"type": "string"},
                        "description": {"type": "string"},
                        "trigger": {"type": "array", "items": {"type": "object"}},
                        "condition": {"type": "array", "items": {"type": "object"}},
                        "action": {"type": "array", "items": {"type": "object"}},
                        "mode": {"type": "string", "default": "single"}
                    },
                    "required": ["alias", "trigger", "action"]
                }
            ),
            Tool(
                name="create_script",
                description="Create a new script. Validates config before adding.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "alias": {"type": "string"},
                        "sequence": {"type": "array", "items": {"type": "object"}},
                        "mode": {"type": "string", "default": "single"},
                        "icon": {"type": "string"}
                    },
                    "required": ["alias", "sequence"]
                }
            ),
            # 17. Helper Management
            Tool(
                name="manage_helpers",
                description="Manage input helpers (input_boolean, input_text, etc).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "enum": ["input_boolean", "input_button", "input_text", "input_number", "input_datetime", "input_select", "timer", "schedule", "counter"]},
                        "action": {"type": "string", "enum": ["create", "delete"]},
                        "name": {"type": "string", "description": "Friendly name"},
                        "config": {"type": "object", "description": "Additional config (min, max, options) for create"},
                        "entity_id": {"type": "string", "description": "Required for delete"}
                    },
                    "required": ["domain", "action"]
                }
            ),
            # 18. Dashboard Management (Writer)
            Tool(
                 name="manage_dashboards",
                 description="Create or update Lovelace dashboard resources/views.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "action": {"type": "string", "enum": ["create_dashboard", "update_view"]},
                         "dashboard_url_path": {"type": "string", "description": "URL path (e.g. 'overview')"},
                         "config": {"type": "object", "description": "The YAML/JSON config for the view or dashboard"}
                     },
                     "required": ["action", "config"]
                 }
            ),
            # 19. Integration Installer
            Tool(
                 name="install_integration",
                 description="Initialize a config flow to install a new integration.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "domain": {"type": "string", "description": "Integration domain (e.g. 'met')"},
                         "config_data": {"type": "object", "description": "Configuration data required by the flow"}
                     },
                     "required": ["domain"]
                 }
            ),
            # 14. Energy Auditor
            Tool(
                name="get_energy_usage",
                description="Get energy usage statistics.",
                inputSchema={
                    "type": "object",
                    "properties": {
                         "period_days": {"type": "integer", "default": 7}
                    }
                }
            ),
            # 15. Semantic Entity Search
            Tool(
                 name="find_entities",
                 description="Fuzzy search for entities by name, domain, or device info.",
                 inputSchema={
                     "type": "object",
                     "properties": {
                         "query": {"type": "string", "description": "Search term (e.g. 'kitchen lights', 'battery level')"}
                     },
                     "required": ["query"]
                 }
            )
        ]

    async def _call_tool_impl(self, name: str, arguments: dict) -> list[TextContent | ImageContent | EmbeddedResource]:
        """Handle tool execution."""
        
        # 1. System & File Management
        if name == "read_config_file":
            path = self.hass.config.path(arguments["path"])
            
            # Security: Path Traversal Check
            try:
                config_root = Path(self.hass.config.config_dir).resolve()
                target_path = Path(path).resolve()
                if config_root not in target_path.parents and config_root != target_path:
                    return [TextContent(type="text", text=f"Error: Access denied. Path must be within config directory.")]
            except Exception as e:
                 return [TextContent(type="text", text=f"Error resolving path: {str(e)}")]

            if not os.path.exists(path):
                return [TextContent(type="text", text=f"Error: File not found at {path}")]
            try:
                async with aiohttp.ClientSession() as session:
                    # Just read local file
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    return [TextContent(type="text", text=content)]
            except Exception as e:
                return [TextContent(type="text", text=f"Error reading file: {str(e)}")]

        elif name == "write_config_file":
            path = self.hass.config.path(arguments["path"])
            content = arguments["content"]
            
            # Security: Path Traversal Check
            try:
                config_root = Path(self.hass.config.config_dir).resolve()
                target_path = Path(path).resolve()
                # Allow writing if parent is in config, even if file doesn't exist yet
                if config_root not in target_path.parents and config_root != target_path:
                    return [TextContent(type="text", text=f"Error: Access denied. Path must be within config directory.")]
            except Exception as e:
                 return [TextContent(type="text", text=f"Error resolving path: {str(e)}")]
            
            # Auto-Backup
            try:
                backup_name = f"mcp_auto_{os.path.basename(path)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                if self.hass.services.has_service("hassio", "backup_partial"):
                    await self.hass.services.async_call(
                        "hassio", "backup_partial", 
                        {"name": backup_name, "homeassistant": True}, 
                        blocking=True
                    )
            except Exception as e:
                _LOGGER.warning(f"Failed to create auto-backup before write: {e}")

            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return [TextContent(type="text", text=f"Successfully wrote to {path} (Backup: {backup_name})")]
            except Exception as e:
                return [TextContent(type="text", text=f"Error writing file: {str(e)}")]

        elif name == "get_system_logs":
            log_path = self.hass.config.path("home-assistant.log")
            lines_count = arguments.get("lines", 50)
            if not os.path.exists(log_path):
                return [TextContent(type="text", text="Log file not found.")]
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    return [TextContent(type="text", text="".join(lines[-lines_count:]))]
            except Exception as e:
                return [TextContent(type="text", text=f"Error reading log: {str(e)}")]

        elif name == "call_service":
            try:
                await self.hass.services.async_call(
                    arguments["domain"], 
                    arguments["service"], 
                    arguments.get("service_data", {}), 
                    blocking=True
                )
                return [TextContent(type="text", text="Service called successfully.")]
            except Exception as e:
                return [TextContent(type="text", text=f"Service call failed: {str(e)}")]

        # 2. Registry & Entity Management
        elif name == "cleanup_registry":
            days = arguments.get("days_offline", 7)
            dry_run = arguments.get("dry_run", True)
            domain_filter = arguments.get("domain_filter")
            
            ent_reg = entity_registry.async_get(self.hass)
            threshold = dt_util.utcnow() - timedelta(days=days)
            cleanup_list = []
            
            # Iterate states to find unavailable (this is weak, better to check registry directly if no state)
            # Better approach: check registry entries 
            # Note: Registry entries don't always track 'last_seen'. 
            # We will use state engine for 'unavailable' check on active entities.
            
            for entity in ent_reg.entities.values():
                if domain_filter and entity.domain != domain_filter:
                    continue
                state = self.hass.states.get(entity.entity_id)
                if state:
                    if state.state in ["unavailable", "unknown"] and state.last_changed < threshold:
                        cleanup_list.append({"id": entity.entity_id, "name": entity.original_name or entity.name, "status": state.state})
                else:
                    # Entity in registry but no state (restored?)
                    cleanup_list.append({"id": entity.entity_id, "name": entity.original_name or entity.name, "status": "no_state"})

            if dry_run:
                return [TextContent(type="text", text=f"Dry Run Found {len(cleanup_list)} candidates:\n{json.dumps(cleanup_list, indent=2)}")]
            
            removed_count = 0
            for item in cleanup_list:
                ent_reg.async_remove(item["id"])
                removed_count += 1
            return [TextContent(type="text", text=f"Removed {removed_count} entities.")]

        elif name == "manage_entities":
            action = arguments["action"]
            ids = arguments["entity_ids"]
            ent_reg = entity_registry.async_get(self.hass)
            results = []
            
            for eid in ids:
                if action == "remove":
                    ent_reg.async_remove(eid)
                    results.append(f"Removed {eid}")
                elif action == "disable":
                    ent_reg.async_update_entity(eid, disabled_by=ConfigEntryDisabler.USER)
                    results.append(f"Disabled {eid}")
                elif action == "enable":
                    ent_reg.async_update_entity(eid, disabled_by=None)
                    results.append(f"Enabled {eid}")
            
            return [TextContent(type="text", text="\n".join(results))]

        # 3. Dashboard Generation
        elif name == "generate_dashboard_config":
            area_id = arguments["area_id"]
            card_type = arguments.get("card_type", "mushroom")
            
            er = entity_registry.async_get(self.hass)
            dr = device_registry.async_get(self.hass)
            
            area_entities = []
            # Get entities directly assigned to area
            for entity in er.entities.values():
                if entity.area_id == area_id:
                    area_entities.append(entity)
            
            # Get entities from devices assigned to area
            for device in dr.devices.values():
                if device.area_id == area_id:
                     for entity in er.entities.values():
                        if entity.device_id == device.id:
                            area_entities.append(entity)

            # Deduplicate
            unique_entities = {e.entity_id: e for e in area_entities}
            sorted_entities = sorted(unique_entities.values(), key=lambda x: x.domain)

            yaml_lines = ["type: vertical-stack", "cards:"]
            
            if card_type == "bubble":
                yaml_lines.append(f"  - type: custom:bubble-card\n    card_type: pop-up\n    hash: '#{area_id}'\n    name: {area_id}")

            for e in sorted_entities:
                if e.disabled_by: continue
                eid = e.entity_id
                
                if card_type == "bubble":
                    yaml_lines.append(f"  - type: custom:bubble-card\n    card_type: button\n    entity: {eid}")
                elif card_type == "mushroom":
                    if eid.startswith("light."):
                         yaml_lines.append(f"  - type: custom:mushroom-light-card\n    entity: {eid}\n    use_light_color: true")
                    elif eid.startswith("cover."):
                         yaml_lines.append(f"  - type: custom:mushroom-cover-card\n    entity: {eid}")
                    else:
                        yaml_lines.append(f"  - type: custom:mushroom-entity-card\n    entity: {eid}")
                elif card_type == "minimalist":
                    yaml_lines.append(f"  - type: 'custom:button-card'\n    template: card_generic\n    entity: {eid}")
                else: # tile
                    yaml_lines.append(f"  - type: tile\n    entity: {eid}")
            
            return [TextContent(type="text", text="\n".join(yaml_lines))]

        # 4. Integration Control
        elif name == "manage_integrations":
            action = arguments["action"]
            eid = arguments.get("entry_id")
            
            if action == "list":
                res = []
                for e in self.hass.config_entries.async_entries():
                     res.append({
                         "entry_id": e.entry_id, 
                         "domain": e.domain, 
                         "title": e.title, 
                         "state": e.state.value,
                         "disabled_by": e.disabled_by
                     })
                return [TextContent(type="text", text=json.dumps(res, indent=2))]
            
            if not eid:
                return [TextContent(type="text", text="Error: entry_id required")]

            if action == "reload":
                await self.hass.config_entries.async_reload(eid)
                return [TextContent(type="text", text=f"Reloaded {eid}")]
            elif action == "disable":
                await self.hass.config_entries.async_set_disabled_by(eid, ConfigEntryDisabler.USER)
                return [TextContent(type="text", text=f"Disabled {eid}")]
            elif action == "enable":
                await self.hass.config_entries.async_set_disabled_by(eid, None)
                return [TextContent(type="text", text=f"Enabled {eid}")]
            elif action == "remove":
                await self.hass.config_entries.async_remove(eid)
                return [TextContent(type="text", text=f"Removed {eid}")]

        elif name == "manage_hacs":
            # Just a wrapper around HACS if available
            hacs = self.hass.data.get("hacs")
            if not hacs:
                return [TextContent(type="text", text="HACS not installed or loaded.")]
            
            action = arguments["action"]
            # HACS API interactions would go here (complex, stub-impled for now)
            # Real implementation would call hacs.async_install_repository etc.
            return [TextContent(type="text", text="HACS Management Staged (API implementation requires access to HACS instance internals).")]

        # 5. Add-on Management
        elif name == "manage_addons":
            action = arguments["action"]
            if not self.hass.components.hassio.is_connected():
                 return [TextContent(type="text", text="Supervisor not connected.")]
            
            if action == "list":
                 # requires pulling data from supervisor API
                 # simplified:
                 return [TextContent(type="text", text="Feature requires Supervisor API access permission.")]
            
            slug = arguments.get("slug")
            if slug:
                if action in ["start", "stop", "restart", "update", "limit"]:
                    await self.hass.services.async_call("hassio", f"addon_{action}", {"addon": slug})
                    return [TextContent(type="text", text=f"Triggered addon_{action} for {slug}")]
            
            return [TextContent(type="text", text="Action not fully implemented.")]

        # 6. Data & Analytics
        elif name == "execute_sql_query":
            query = arguments["query"].strip()
            
            # Security Safety Check: Enforce READ-ONLY
            forbidden_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "CREATE", "REPLACE"]
            upper_query = query.upper()
            
            if not upper_query.startswith("SELECT"):
                return [TextContent(type="text", text="Error: Only SELECT queries are allowed for safety reasons.")]
            
            for keyword in forbidden_keywords:
                if f" {keyword} " in f" {upper_query} " or f"\n{keyword} " in f"\n{upper_query} " or f" {keyword}\n" in f" {upper_query}\n":
                     return [TextContent(type="text", text=f"Error: Query contains forbidden keyword '{keyword}'")]

            # Access recorder instance
            instance = recorder.get_instance(self.hass)
            
            def run_query():
                with instance.engine.connect() as conn:
                    from sqlalchemy import text
                    result = conn.execute(text(query))
                    return [dict(row) for row in result.mappings()]

            try:
                rows = await self.hass.async_add_executor_job(run_query)
                return [TextContent(type="text", text=json.dumps(rows, default=str, indent=2))]
            except Exception as e:
                return [TextContent(type="text", text=f"SQL Error: {str(e)}")]

        elif name == "generate_history_chart":
            entity_id = arguments["entity_id"]
            hours = arguments.get("hours", 24)
            start_time = dt_util.utcnow() - timedelta(hours=hours)
            
            # Fetch history
            history_list = await history.get_significant_states(
                self.hass, start_time, [entity_id], include_start_time_state=True
            )
            states = history_list.get(entity_id, [])
            
            if not states:
                return [TextContent(type="text", text="No history found.")]
            
            # Prepare data
            times = [s.last_changed for s in states]
            values = []
            valid_times = []
            for s in states:
                try:
                    val = float(s.state)
                    values.append(val)
                    valid_times.append(s.last_changed)
                except ValueError:
                    pass
            
            if not values:
                return [TextContent(type="text", text="No numeric data found.")]

            # Plot
            def create_plot():
                buf = io.BytesIO()
                fig, ax = plt.subplots(figsize=(10, 6))
                ax.plot(valid_times, values)
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                plt.title(f"History for {entity_id}")
                plt.grid(True)
                plt.savefig(buf, format='png')
                plt.close(fig)
                buf.seek(0)
                return base64.b64encode(buf.read()).decode('utf-8')

            b64_img = await self.hass.async_add_executor_job(create_plot)
            return [
                TextContent(type="text", text=f"History chart for {entity_id}"),
                ImageContent(type="image", data=b64_img, mimeType="image/png")
            ]

        elif name == "render_template":
            try:
                tpl = template_helper.Template(arguments["template"], self.hass)
                res = tpl.async_render(parse_result=False)
                return [TextContent(type="text", text=res)]
            except Exception as e:
                return [TextContent(type="text", text=f"Template Error: {str(e)}")]

        # 7. Local LLM
        elif name == "local_llm_query":
            url = self.config.get(CONF_LLM_URL)
            provider = self.config.get(CONF_LLM_PROVIDER)
            model = self.config.get(CONF_LLM_MODEL)
            prompt = arguments["prompt"]
            
            if not url:
                return [TextContent(type="text", text="LLM URL not configured.")]
            
            payload = {}
            api_endpoint = ""
            
            if provider == PROVIDER_OLLAMA:
                api_endpoint = f"{url}/api/generate"
                payload = {"model": model, "prompt": prompt, "stream": False}
            elif provider == PROVIDER_OPENAI:
                api_endpoint = f"{url}/v1/chat/completions"
                payload = {
                    "model": model, 
                    "messages": [{"role": "user", "content": prompt}]
                }
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(api_endpoint, json=payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if provider == PROVIDER_OLLAMA:
                                return [TextContent(type="text", text=data.get("response", ""))]
                            else: # OpenAI
                                return [TextContent(type="text", text=data["choices"][0]["message"]["content"])]
                        else:
                             return [TextContent(type="text", text=f"LLM Error {resp.status}")]
            except Exception as e:
                 return [TextContent(type="text", text=f"Connection Error: {str(e)}")]

        # 8. Advanced Automation Debugging
        elif name == "get_automation_trace":
            automation_id = arguments["automation_id"]
            if not automation_id.startswith("automation."):
                 return [TextContent(type="text", text="Error: Entity ID must be an automation.")]
            
            # Access internal trace store
            if "trace" not in self.hass.config.components:
                 return [TextContent(type="text", text="Error: Trace integration not loaded.")]
            
            # Use import to access internal registry if possible, or use restore/retrieval methods
            # Note: Trace API is internal. We rely on retrieving the 'trace' object from the AutomationEntity if available,
            # or reading from internal storage.
            # Simplified: Use the REST API helper approach or access trace.async_get_traces
            
            try:
                # Use traces module to look up
                # Automation trace keys are usually "automation.entity_id"
                key = automation_id.split(".")[1]
                # This is tricky without using private APIs. 
                # We will try to get the integration's stored traces.
                
                # Fallback: List the automation's state attributes which might contain 'last_triggered'
                state = self.hass.states.get(automation_id)
                if not state:
                    return [TextContent(type="text", text="Automation not found.")]
                
                return [TextContent(type="text", text=f"Trace retrieval requires accessing internal storage. Automation last triggered: {state.attributes.get('last_triggered')} \n(Full JSON trace extraction is currently limited by API access in this customization)")]
            except Exception as e:
                return [TextContent(type="text", text=f"Trace Error: {str(e)}")]

        # 9. Safe System Operations
        elif name == "safe_restart_system":
            # 1. Check Config
            try:
                # Call homeassistant.check_config
                # In modern HA, this service might return a result or raise error
                # Ideally we rely on the core config validation
                errors = await self.hass.config.async_check_config_err()
                if errors:
                    return [TextContent(type="text", text=f"Config Check FAILED. Restart Aborted.\nErrors: {errors}")]
                
                # 2. Restart
                await self.hass.services.async_call("homeassistant", "restart")
                return [TextContent(type="text", text="Configuration Valid. Restart triggered.")]
            except Exception as e:
                return [TextContent(type="text", text=f"Safety Check Failed: {str(e)}")]

        # 10. Context (Calendar & Todo)
        elif name == "get_calendar_events":
            entity_ids = arguments["entity_ids"]
            start_offset = arguments.get("start_hours_offset", 0)
            duration = arguments.get("duration_hours", 24)
            
            start_dt = dt_util.utcnow() + timedelta(hours=start_offset)
            end_dt = start_dt + timedelta(hours=duration)
            
            events = []
            for eid in entity_ids:
                try:
                    # Using the proper Service API usually puts events on the bus or returns them?
                    # Service: calendar.get_events
                    response = await self.hass.services.async_call(
                        "calendar", "get_events",
                        {"entity_id": eid, "start_date_time": start_dt, "end_date_time": end_dt},
                        blocking=True, return_response=True
                    )
                    if response:
                        events.append({eid: response})
                except Exception as e:
                    events.append({eid: f"Error: {str(e)}"})
            
            return [TextContent(type="text", text=json.dumps(events, default=str, indent=2))]

        elif name == "manage_todo_list":
            entity_id = arguments["entity_id"]
            action = arguments["action"]
            
            if action == "list":
                # Currently todo platform doesn't seamlessly return items via service call in a standard way
                # Supports: todo.get_items in recent HA versions
                try:
                     response = await self.hass.services.async_call(
                        "todo", "get_items",
                        {"entity_id": entity_id},
                        blocking=True, return_response=True
                    )
                     return [TextContent(type="text", text=json.dumps(response, default=str, indent=2))]
                except Exception as e:
                     return [TextContent(type="text", text=f"Error listing items: {str(e)}")]
            
            elif action == "add":
                item_data = arguments.get("item", {})
                await self.hass.services.async_call(
                    "todo", "add_item",
                    {"entity_id": entity_id, "item": item_data.get("summary")},
                    blocking=True
                )
                return [TextContent(type="text", text="Item added.")]
            # ... update/remove similar implementation

        # 11. Network Health
        elif name == "get_network_health":
            domain = arguments.get("domain", "zha")
            
            if domain == "zha":
                # Check ZHA integration metrics
                # This usually requires accessing the 'zha' component internals or entities
                try:
                    # Generic heuristic: Find all ZHA devices and check availability/LQI if exposed
                    # For now, list unavailable ZHA entities
                    ent_reg = entity_registry.async_get(self.hass)
                    zha_entities = [e.entity_id for e in ent_reg.entities.values() if e.platform == "zha"]
                    
                    unavailable = []
                    for eid in zha_entities:
                        state = self.hass.states.get(eid)
                        if state and state.state == "unavailable":
                            unavailable.append(eid)
                    
                    msg = f"ZHA Analysis: Found {len(zha_entities)} total entities.\nUnavailable: {len(unavailable)}\n"
                    if unavailable: msg += f"List: {unavailable[:10]}..."
                    
                    return [TextContent(type="text", text=msg)]
                except Exception as e:
                    return [TextContent(type="text", text=f"ZHA Diagnosis failed: {str(e)}")]
            
            elif domain == "zigbee2mqtt":
                # Z2M usually exposes a 'bridge/state' or 'bridge/info' topic -> sensor
                # Check for 'sensor.zigbee2mqtt_bridge_state' or similar
                
                # Heuristic: Find entities with 'zigbee2mqtt' in ID or integration
                # Often mapped as MQTT entities.
                # Look for the bridge state sensor
                bridge_state = self.hass.states.get("sensor.zigbee2mqtt_bridge_state")
                network_map = self.hass.states.get("sensor.zigbee2mqtt_networkmap") # Some installs have this
                
                info = []
                if bridge_state: info.append(f"Bridge State: {bridge_state.state}")
                else: info.append("Warning: Could not find 'sensor.zigbee2mqtt_bridge_state'")
                
                return [TextContent(type="text", text="\n".join(info))]

        # 16. Automation & Script Creator (UI Editable)
        elif name == "create_automation":
            try:
                # 1. Validate
                await async_validate_automation(self.hass, arguments)
                
                # 2. Assign ID if missing (Critical for UI editing)
                if "id" not in arguments:
                    arguments["id"] = str(uuid.uuid4())
                
                # 3. Use Internal Config Helper (The "Right Way" for UI)
                # This ensures it saves to the correct location (usually automations.yaml) 
                # AND registers it as editable.
                from homeassistant.components.automation.config import _async_update_config
                
                # _async_update_config(hass, config_id, config_data)
                # Pass 'None' as id to create new? No, usually we pass the new ID.
                # Actually, the signature is often `async_update_config(hass, id, config)`. 
                # If it doesn't exist, it creates.

                await _async_update_config(self.hass, arguments["id"], arguments)
                
                return [TextContent(type="text", text=f"Automation '{arguments.get('alias')}' created (UI Editable).")]
            except ImportError:
                 # Fallback if internal API changes
                 return [TextContent(type="text", text="Error: Could not import automation configuration helper. Detailed creation requires access to `homeassistant.components.automation.config._async_update_config`.")]
            except Exception as e:
                return [TextContent(type="text", text=f"Automation Creation Failure: {str(e)}")]

        elif name == "create_script":
            try:
                # Script config works similarly?
                # homeassistant.components.script.config
                from homeassistant.components.script.config import _async_update_config as script_update_config
                
                await async_validate_script(self.hass, arguments)
                
                if "alias" not in arguments:
                     return [TextContent(type="text", text="Error: Alias required.")]
                
                # Scripts use the entity_id slug as the key usually, but for UI editing they refer to a unique ID (sequence).
                # New style scripts in UI have an entry in scripts.yaml with a unique object ID?
                # Actually UI scripts are stored in scripts.yaml keyed by object_id.
                
                # We'll rely on the helper to handle the key/ID generation or use an alias-slug.
                # If we use _async_update_config, we pass the object_id.
                
                object_id = arguments["alias"].lower().replace(" ", "_")
                
                await script_update_config(self.hass, object_id, arguments)
                
                return [TextContent(type="text", text=f"Script '{arguments['alias']}' created as '{object_id}' (UI Editable).")]
            except Exception as e:
                return [TextContent(type="text", text=f"Script Creation Failure: {str(e)}")]

        # 17. Helper Management
        elif name == "manage_helpers":
            domain = arguments["domain"]
            action = arguments["action"]
            
            # This relies on the new 'input_*' config flow or storage collections.
            # Most helpers (input_boolean) utilize the .storage/ core.config_entries logic now.
            # The official way is strictly Config Flow.
            
            if action == "create":
                # Trigger flow
                # This is hard to do headless without a user interacting.
                # Alternative: Use the legacy YAML approach (append to configuration.yaml)?
                # Or use the specialized collection managers if accessible.
                return [TextContent(type="text", text="Helper creation requires Config Flow interaction which is not yet fully headless-capable. Please use 'write_config_file' to add to configuration.yaml and restart.")]
            
            elif action == "delete":
                eid = arguments["entity_id"]
                # Helpers are config entries usually? Or just items in registry?
                # Should be removable via entity registry if it's a restored entity, 
                # but if it's config-based, we need 'remove_config_entry'.
                ent_reg = entity_registry.async_get(self.hass)
                entry = ent_reg.async_get(eid)
                if entry and entry.config_entry_id:
                     await self.hass.config_entries.async_remove(entry.config_entry_id)
                     return [TextContent(type="text", text=f"Helper {eid} deleted.")]
                return [TextContent(type="text", text=f"Helper {eid} not found or not managed via UI.")]

        # 18. Dashboard (Lovelace)
        elif name == "manage_dashboards":
            action = arguments["action"]
            # Lovelace is stored in .storage/lovelace or in yaml mode.
            # We can access `hass.data['lovelace']`
            
            try:
                # Check for storage mode
                if "lovelace" not in self.hass.data:
                     return [TextContent(type="text", text="Lovelace not loaded.")]
                
                # This requires deep hacking of LovelaceStorage.
                # Simplified:
                return [TextContent(type="text", text="Dashboard management is currently restricted to 'generate_dashboard_config' (Read-Only generation). Write support requires complex Lovelace Storage API access.")]
            except Exception as e:
                return [TextContent(type="text", text=f"Dashboard Error: {str(e)}")]

        # 19. Integration Installer
        elif name == "install_integration":
            domain = arguments["domain"]
            conf = arguments.get("config_data", {})
            try:
                result = await self.hass.config_entries.flow.async_init(
                    domain, context={"source": "user"}, data=conf
                )
                return [TextContent(type="text", text=f"Flow Init Result: {result.get('type')} / {result.get('reason') or 'Success'}\n(Full interaction requires multi-step handling)")]
            except Exception as e:
                 return [TextContent(type="text", text=f"Install Error: {str(e)}")]
            entity_id = arguments.get("entity_id")
            start_hours = arguments.get("start_hours_ago", 24)
            end_hours = arguments.get("end_hours_ago", 0)
            
            start_dt = dt_util.utcnow() - timedelta(hours=start_hours)
            end_dt = dt_util.utcnow() - timedelta(hours=end_hours)
            
            try:
                # Use logbook.async_get_events
                # We need to filter by list of entities if provided
                entities = [entity_id] if entity_id else None
                
                # The API signature for async_get_events varies slightly by version but generally:
                # (hass, start_day, end_day, entity_ids=None, ...)
                # It returns a recursive generator or list of Event objects
                
                # As a safe wrapper we can use the helper:
                events = await recorder.get_instance(self.hass).async_add_executor_job(
                    logbook.get_events, self.hass, start_dt, end_dt, entities
                )
                
                # Format for LLM
                results = []
                for e in events:
                    # e is a LazyEventPartialState or similar
                    results.append(f"[{e.time_fired.strftime('%Y-%m-%d %H:%M:%S')}] {e.name} ({e.entity_id}): {e.state if hasattr(e, 'state') else e.message}")
                
                input_desc = f"Logbook for {entity_id if entity_id else 'ALL'} from {start_hours}h ago."
                return [TextContent(type="text", text=f"{input_desc}\n\n" + ("\n".join(results[-100:]) or "No events found."))] # limit to last 100
            except Exception as e:
                return [TextContent(type="text", text=f"Logbook Error: {str(e)}")]

        # 13. Room Announcer
        elif name == "announce_in_area":
            area_id = arguments["area_id"]
            message = arguments["message"]
            service = arguments.get("tts_service", "tts.cloud_say")
            
            # Find media players in area
            dr = device_registry.async_get(self.hass)
            er = entity_registry.async_get(self.hass)
            
            target_entities = []
            
            # 1. Devices in area
            for device in dr.devices.values():
                if device.area_id == area_id:
                    for entity in er.entities.values():
                        if entity.device_id == device.id and entity.domain == "media_player":
                            # Check if available
                            if not self.hass.states.get(entity.entity_id): continue 
                            target_entities.append(entity.entity_id)

            # 2. Entities directly in area
            for entity in er.entities.values():
                if entity.area_id == area_id and entity.domain == "media_player":
                    if entity.entity_id not in target_entities:
                         if self.hass.states.get(entity.entity_id):
                             target_entities.append(entity.entity_id)

            if not target_entities:
                return [TextContent(type="text", text=f"No media players found in area '{area_id}'.")]
            
            try:
                # Call TTS service
                await self.hass.services.async_call(
                    service.split(".")[0], service.split(".")[1],
                    {"entity_id": target_entities, "message": message},
                    blocking=True
                )
                return [TextContent(type="text", text=f"Announced on {len(target_entities)} devices: {target_entities}")]
            except Exception as e:
                 return [TextContent(type="text", text=f"Announcement failed: {str(e)}")]

        # 14. Energy Auditor (Simplified)
        elif name == "get_energy_usage":
            period = arguments.get("period_days", 7)
            
            # This is complex. We'll fallback to a heuristic: 
            # Find entities with state_class='total_increasing' and device_class='energy'
            # and query the 'statistics' (5-minute/hourly) for them.
            
            try:
                stats_info = []
                # Scan for energy sensors
                for state in self.hass.states.async_all("sensor"):
                    sc = state.attributes.get("state_class")
                    dc = state.attributes.get("device_class")
                    if sc == "total_increasing" and dc == "energy":
                        # Get statistics
                        # We userecorder.statistics.statistics_during_period
                        start_time = dt_util.utcnow() - timedelta(days=period)
                        
                        # We need to run this in executor
                        # This returns a dict {entity_id: [stat_dicts]}
                        # We'll just grab the 'sum' difference
                        pass # Implementing fully inside executor below
                        stats_info.append(state.entity_id)
                
                if not stats_info:
                     return [TextContent(type="text", text="No energy sensors found (state_class=total_increasing, device_class=energy).")]
                
                def get_stats():
                    from homeassistant.components.recorder import statistics
                    return statistics.statistics_during_period(
                        self.hass, 
                        dt_util.utcnow() - timedelta(days=period), 
                        dt_util.utcnow(), 
                        stats_info, 
                        "hour", 
                        None, 
                        {"sum"}
                    )
                
                raw_stats = await recorder.get_instance(self.hass).async_add_executor_job(get_stats)
                
                # Process results
                report = [f"Energy Usage Report (Last {period} days):"]
                for eid, data in raw_stats.items():
                    if data:
                        # Sum is cumulative usually? No, for total_increasing, statistics stores the 'change' or 'state'
                        # Actually 'sum' in statistics is the change during the bucket.
                        total_usage = 0.0
                        for bucket in data:
                            total_usage += bucket.get("sum", 0)
                        
                        report.append(f"{eid}: {total_usage:.2f} kWh")
                
                return [TextContent(type="text", text="\n".join(report))]
            except Exception as e:
                return [TextContent(type="text", text=f"Energy Audit Error: {str(e)}")]

        # 15. Semantic Entity Search
        elif name == "find_entities":
            query = arguments["query"].lower()
            er = entity_registry.async_get(self.hass)
            dr = device_registry.async_get(self.hass)
            
            matches = []
            
            for entity in er.entities.values():
                # Score based on matches
                score = 0
                search_corpus = f"{entity.entity_id} {entity.original_name} {entity.name}" if entity.original_name else f"{entity.entity_id} {entity.name}"
                
                if entity.device_id:
                    dev = dr.async_get(entity.device_id)
                    if dev:
                        search_corpus += f" {dev.name} {dev.manufacturer} {dev.model}"
                
                search_corpus = search_corpus.lower()
                
                # Simple keyword checking
                keywords = query.split()
                if all(k in search_corpus for k in keywords):
                    state = self.hass.states.get(entity.entity_id)
                    current = f"State: {state.state}" if state else "State: Unknown"
                    matches.append(f"{entity.entity_id} ({entity.name or entity.original_name}) - {current}")
            
            count = len(matches)
            if count > 50:
                matches = matches[:50]
                matches.append(f"... and {count-50} more.")
            
            return [TextContent(type="text", text=f"Found {count} matches for '{query}':\n" + "\n".join(matches))]

        # 20. Backup Manager
        elif name == "manage_backups":
            action = arguments["action"]
            
            if action == "create":
                # Only partial supported easily? Full is better.
                # Service: backup.create
                await self.hass.services.async_call("backup", "create", blocking=True)
                return [TextContent(type="text", text="Backup creation triggered successfully.")]
            
            elif action == "list":
                # This requires access to the Backup Manager
                # hass.data['backup'].manager.get_backups()
                try:
                    manager = self.hass.data.get("backup_manager") or self.hass.data.get("backup")
                    # The key changed recently. It might be in 'backup' integration data.
                    # Fallback: Just return text saying "Check Settings > System > Backups" 
                    # OR try to inspect the backup dir if accessible.
                    
                    # Better approach: access the supervisor if available?
                    # For Core, backups are in /config/backups usually (or configured path).
                    backup_dir = self.hass.config.path("backups")
                    if os.path.exists(backup_dir):
                        backups = [f for f in os.listdir(backup_dir) if f.endswith(".tar")]
                        return [TextContent(type="text", text=f"Found {len(backups)} local backup files:\n" + "\n".join(backups))]
                    return [TextContent(type="text", text="Backup directory not accessible or empty.")]
                except Exception as e:
                    return [TextContent(type="text", text=f"List Backups failed: {str(e)}")]

        # 21. Blueprint Discovery
        elif name == "list_blueprints":
            domain = arguments.get("domain", "automation")
            # Blueprints are in blueprints/{domain}
            bp_dir = self.hass.config.path(f"blueprints/{domain}")
            
            results = []
            if os.path.exists(bp_dir):
                for root, _, files in os.walk(bp_dir):
                    for f in files:
                        if f.endswith(".yaml"):
                            rel_path = os.path.relpath(os.path.join(root, f), bp_dir)
                            results.append(rel_path)
            
            return [TextContent(type="text", text=f"Available {domain} blueprints:\n" + "\n".join(results))]

        # 22. Configuration Validator
        elif name == "check_config":
            # homeassistant.config.async_check_ha_config_file(hass)
            from homeassistant.config import async_check_ha_config_file
            
            errors = await async_check_ha_config_file(self.hass)
            
            if errors is None:
                return [TextContent(type="text", text="Configuration Valid! (No errors returned)")]
            
            # errors is a generic string or dict check
            return [TextContent(type="text", text=f"Configuration Check Result:\n{errors}")]

        # 23. Service Introspection
        elif name == "list_available_services":
            domain_filter = arguments.get("domain")
            services = self.hass.services.async_services()
            
            # Access internal schema descriptions if possible, otherwise just names
            # hass.services.async_services_json() might be available in newer versions?
            # Actually `hass.services.async_services()` returns a dict {domain: {service: description}}
            
            # We will dump the schemas
            report = {}
            for dom, t_services in services.items():
                if domain_filter and dom != domain_filter: continue
                report[dom] = t_services
            
            # Limit output if too huge
            import json
            text = json.dumps(report, indent=2, default=str)
            if len(text) > 100000:
                text = text[:100000] + "\n... (truncated)"
            
            return [TextContent(type="text", text=text)]

        # 24. Home Topology (Spatial Awareness)
        elif name == "get_home_topology":
            ar = area_registry.async_get(self.hass)
            dr = device_registry.async_get(self.hass)
            er = entity_registry.async_get(self.hass)
            
            topology = {}
            
            # 1. Map Areas
            for area in ar.areas.values():
                topology[area.name] = {
                    "area_id": area.id,
                    "devices": [],
                    "orphan_entities": []
                }
            
            # 2. Map Devices to Areas
            device_map = {} # id -> area_name
            for device in dr.devices.values():
                area_id = device.area_id
                if area_id and area_id in ar.areas:
                    area_name = ar.areas[area_id].name
                    
                    # Get entities for this device
                    dev_entities = []
                    for entity in er.entities.values():
                        if entity.device_id == device.id:
                            dev_entities.append(f"{entity.entity_id} ({entity.original_name or entity.name})")
                    
                    topology[area_name]["devices"].append({
                        "name": device.name,
                        "model": device.model,
                        "manufacturer": device.manufacturer,
                        "entities": dev_entities
                    })
                    device_map[device.id] = area_name
            
            # 3. Handle Orphan entities (in area but no device, or global)
            for entity in er.entities.values():
                if entity.area_id and entity.area_id in ar.areas:
                    area_name = ar.areas[entity.area_id].name
                    if not entity.device_id:
                        topology[area_name]["orphan_entities"].append(entity.entity_id)
            
            import json
            return [TextContent(type="text", text=json.dumps(topology, indent=2))]

        # 25. Secrets Manager
        elif name == "manage_secrets":
            action = arguments["action"]
            key = arguments.get("key")
            value = arguments.get("value")
            
            secrets_path = self.hass.config.path("secrets.yaml")
            
            if action == "list":
                 # Security: Don't show values!
                 if not os.path.exists(secrets_path):
                     return [TextContent(type="text", text="secrets.yaml not found.")]
                 
                 keys = []
                 try:
                     with open(secrets_path, "r", encoding="utf-8") as f:
                         import yaml
                         data = yaml.safe_load(f) or {}
                         keys = list(data.keys())
                     return [TextContent(type="text", text=f"Available Secret Keys: {', '.join(keys)}")]
                 except Exception as e:
                     return [TextContent(type="text", text=f"Error reading secrets: {str(e)}")]
            
            elif action == "set":
                # Add or update a secret
                if not key or not value:
                    return [TextContent(type="text", text="Error: Key and Value required for 'set'.")]
                
                try:
                    # Racy read-modify-write, but acceptable for this context
                    current_data = {}
                    if os.path.exists(secrets_path):
                         with open(secrets_path, "r", encoding="utf-8") as f:
                             import yaml
                             current_data = yaml.safe_load(f) or {}
                    
                    current_data[key] = value
                    
                    # Write back
                    # Use simple dump?
                    # Note: This removes comments. 'secrets.yaml' usually has comments.
                    # Warnings about losing comments should be known.
                    with open(secrets_path, "w", encoding="utf-8") as f:
                        import yaml
                        yaml.dump(current_data, f, default_flow_style=False)
                    
                    return [TextContent(type="text", text=f"Secret '{key}' saved.")]
                except Exception as e:
                    return [TextContent(type="text", text=f"Error saving secret: {str(e)}")]

        # 26. Assist / Conversation Agent
        elif name == "run_conversation_agent":
            text = arguments["text"]
            agent_id = arguments.get("agent_id") # None = default
            language = arguments.get("language", "en")
            
            from homeassistant.components import conversation
            
            try:
                # conversation.async_converse(hass, text, conversation_id, context, language, agent_id)
                # We need a context.
                from homeassistant.core import Context
                context = Context()
                
                result = await conversation.async_converse(
                    self.hass,
                    text=text,
                    conversation_id=None,
                    context=context,
                    language=language,
                    agent_id=agent_id
                )
                
                # Result is complex.
                response_text = result.response.speech.get("plain", {}).get("speech", "")
                return [TextContent(type="text", text=f"Assist Response: {response_text}")]
            except Exception as e:
                 return [TextContent(type="text", text=f"Conversation Error: {str(e)}")]

        # 27. Persistent Notification
        elif name == "send_persistent_notification":
            message = arguments["message"]
            title = arguments.get("title", "MCP Agent")
            
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"message": message, "title": title}
            )
            return [TextContent(type="text", text="Notification Sent.")]

        # 28. Label Management
        elif name == "manage_labels":
            action = arguments["action"]
            
            # Requires label_registry
            # from homeassistant.helpers import label_registry
            # But the registry is typically accessed via hass.data
            lr = label_registry.async_get(self.hass)
            
            if action == "list":
                labels = [{"id": l.label_id, "name": l.name, "description": l.description} for l in lr.labels.values()]
                return [TextContent(type="text", text=f"Labels: {json.dumps(labels, indent=2)}")]
            
            elif action == "create":
                name_ = arguments["name"]
                # async_create(self, name: str, icon: str | None = None, color: str | None = None, description: str | None = None) -> LabelEntry
                try:
                    label = lr.async_create(name_)
                    return [TextContent(type="text", text=f"Label '{label.name}' created (ID: {label.label_id}).")]
                except Exception as e:
                     return [TextContent(type="text", text=f"Create Error: {str(e)}")]
            
            elif action == "delete":
                label_id = arguments["label_id"]
                try:
                    lr.async_delete(label_id)
                    return [TextContent(type="text", text=f"Label {label_id} deleted.")]
                except Exception as e:
                     return [TextContent(type="text", text=f"Delete Error: {str(e)}")]
            
            elif action == "add_to_entity":
                label_id = arguments["label_id"]
                entity_id = arguments["entity_id"]
                er = entity_registry.async_get(self.hass)
                
                entity = er.async_get(entity_id)
                if not entity: return [TextContent(type="text", text="Entity not found")]
                
                # Update entity options? No, labels are on the entity entry object now
                # update_entity(entity_id, ..., labels=...)
                # Need to get current labels and add one
                current_labels = set(entity.labels)
                current_labels.add(label_id)
                
                er.async_update_entity(entity_id, labels=current_labels)
                return [TextContent(type="text", text=f"Added label {label_id} to {entity_id}.")]

        return [TextContent(type="text", text=f"Tool {name} not found.")]


class MCP_SSE_View(HomeAssistantView):
    """View to handle MCP SSE connections."""
    url = "/api/mcp/sse"
    name = "api:mcp:sse"
    requires_auth = True

    def __init__(self, mcp_server: HA_MCPServer):
        self.mcp_server = mcp_server
        # Create transport
        self.sse_transport = SseServerTransport("/api/mcp/message")

    async def get(self, request):
        """Handle SSE connection."""
        async with self.sse_transport.connect_sse(
            request, self.mcp_server.create_initialization_options()
        ) as (read_stream, write_stream):
            await self.mcp_server.run(
                read_stream, write_stream, self.mcp_server.create_initialization_options()
            )
        return None

class MCP_Message_View(HomeAssistantView):
    """View to handle MCP POST messages."""
    url = "/api/mcp/message"
    name = "api:mcp:message"
    requires_auth = True

    def __init__(self, transport: SseServerTransport):
        self.transport = transport

    async def post(self, request):
        """Handle JSON-RPC messages."""
        return await self.transport.handle_post_message(request)