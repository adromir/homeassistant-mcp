
# 🏠 Home Assistant MCP Server

![Version](https://img.shields.io/badge/version-1.0.0-blue?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1.0%2B-blue?style=for-the-badge&logo=home-assistant&logoColor=white)

> **Unlock the full potential of Agentic AI in your Smart Home.**

The **Home Assistant MCP Server** is a powerful integration that bridges your Home Assistant instance with the **Model Context Protocol (MCP)**. It transforms your smart home into a set of intelligent tools that AI Agents (like Claude Desktop, IDE Assistants, or local LLMs) can use to **manage, debug, visualize, and control** your system autonomously.

---

## ✨ Features

This integration provides a comprehensive suite of **15+ Tools** categorized for full-system control:

### 🛠️ System Administration
*   **`read_config_file` / `write_config_file`**: Safe, confined access to your `/config` directory.
    *   🛡️ *Safety*: Automatically triggers a **Partial Backup** before any write operation.
    *   🛡️ *Safety*: Sandboxed to prevent access to OS-level files.
*   **`safe_restart_system`**: Performs a robust configuration check before triggering a restart.
*   **`get_system_logs`**: Retrieve recent log entries for debugging.

### � Automation & Logic
*   **`create_automation` / `create_script`**: Create smart home logic directly.
    *   Creates native YAML automations (appended to `automations.yaml`).
    *   Validates configuration against Home Assistant's schema before saving.
*   **`manage_helpers`**: Create or delete input booleans, numbers, and other helpers (Input Helpers).

### 🗣️ Assistant & Feedback
*   **`run_conversation_agent`**: Pass complex natural language commands ("Turn on all lights in the kitchen") to Home Assistant's native Assist (NLU) agent.
*   **`send_persistent_notification`**: Post persistent alerts to the HA dashboard (e.g., "Optimization Complete").

### ⚙️ advanced Configuration
*   **`install_integration`**: Initialize the setup of new integrations (Config Flow) directly from the agent.
*   **`manage_dashboards`**: (Partial) Management of Lovelace dashboard resources.
*   **`check_config`**: Run Home Assistant's core configuration validation to check for health/syntax errors.
*   **`manage_backups`**: Create full system backups or list existing backup files before performing sensitive operations.
*   **`list_blueprints`**: Discover available automation/script blueprints to reuse existing logic.
*   **`manage_secrets`**: Securely read keys (names only) and write values to `secrets.yaml` to avoid hardcoding credentials.

### 🧠 Analytics & Introspection
*   **`list_available_services`**: Query the exact schema of any service to know valid parameters (e.g., "What arguments does `light.turn_on` accept?").
*   **`get_home_topology`**: Generate a spatial knowledge graph (Area -> Device -> Entity) to understand the physical layout of the home.

### 🧹 Registry & Entity Management
*   **`manage_labels`**: Create, delete, and assign Labels (Tags) to organize entities efficiently.
*   **`cleanup_registry`**: "Garbage collection" for your entities. Finds and removes stale/unavailable entities.
*   **`manage_entities`**: Enable, disable, or delete entities programmatically.
*   **`find_entities`**: Fuzzy semantic search ("kitchen lights") to find entity IDs instantly.

### 🔍 Deep Diagnostics (Sherlock Mode)
*   **`get_automation_trace`**: Retrieve detailed JSON traces of failed automations to debug logic errors.
*   **`query_logbook`**: Search the event history (e.g., "When did the door open?") using natural language timeframes.
*   **`get_network_health`**: Diagnose mesh networks. Supports both **ZHA** and **Zigbee2MQTT**.

### 📊 Data & Analytics
*   **`execute_sql_query`**: Run raw (Read-Only) SQL queries against your Recorder database.
*   **`generate_history_chart`**: Generate Matplotlib visualizations of sensor history.
*   **`get_energy_usage`**: Audit your home's energy consumption over time.

### 🎮 Control & Context
*   **`announce_in_area`**: Intelligent TTS that broadcasts messages only to speakers in a specific room.
*   **`manage_integrations` / `manage_addons`**: Full lifecycle control for integrations and Supervisor add-ons.
*   **`get_calendar_events` / `manage_todo_list`**: Give your AI awareness of your schedule and tasks.

---

## 🚀 Installation

### Option 1: HACS (Recommended)

1.  Open **HACS** in Home Assistant.
2.  Go to **Integrations** > **Top Menu (⋮)** > **Custom repositories**.
3.  Add `https://github.com/adromir/homeassistant-mcp` with category **Integration**.
4.  Click **Download**.
5.  Restart Home Assistant.

### Option 2: Manual Installation

1.  Download the latest release.
2.  Copy the `custom_components/ha_mcp_server` folder to your Home Assistant `config/custom_components/` directory.
3.  Restart Home Assistant.

---

## ⚙️ Configuration

1.  Navigate to **Settings** > **Devices & Services**.
2.  Click **+ Add Integration** and search for **"MCP Server for Home Assistant"**.
3.  Follow the setup wizard to configure your Local LLM backend (optional) or just enable the MCP endpoint.

---

## 🛡️ Usage with MCP Clients

This server exposes an **SSE (Server-Sent Events)** endpoint that compatible MCP clients can connect to.

### Connect with Claude Desktop / IDEs

Configure your client to connect to the MCP endpoint:

```json
{
  "mcpServers": {
    "homeassistant": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sse-client",
        "--url",
        "http://YOUR_HA_IP:8123/api/mcp/sse",
        "--headers",
        "{\"Authorization\": \"Bearer YOUR_LONG_LIVED_ACCESS_TOKEN\"}"
      ]
    }
  }
}
```

*Replace `YOUR_HA_IP` and `YOUR_LONG_LIVED_ACCESS_TOKEN` with your actual details.*

---

## ⚠️ Disclaimer

**Use with Caution.** This integration gives AI agents powerful access to your system, including the ability to edit files, delete entities, and restart services.
*   Use the `dry_run` options where available.
*   Ensure your backups are up to date (the auto-backup feature helps, but isn't foolproof).
*   The creators are not responsible for any data loss or system instability caused by autonomous agent actions.

---

## 📄 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ by <strong>Adromir</strong><br>
  <a href="https://github.com/adromir">GitHub Profile</a>
</p>
