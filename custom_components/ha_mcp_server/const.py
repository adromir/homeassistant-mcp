"""Constants for the MCP Server integration."""
DOMAIN = "ha_mcp_server"
DEFAULT_NAME = "HA MCP Server"
# Configuration keys
CONF_LLM_URL = "llm_url"
CONF_LLM_PROVIDER = "llm_provider"
CONF_LLM_MODEL = "llm_model"
# Provider types
PROVIDER_OLLAMA = "ollama"
PROVIDER_KOBOLD = "kobold_cpp"
PROVIDER_OPENAI = "openai_compatible"
DEFAULT_LLM_URL = "http://localhost:11434"
DEFAULT_LLM_MODEL = "llama3"