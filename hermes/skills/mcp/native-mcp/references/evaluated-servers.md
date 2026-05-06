# Evaluated MCP Servers

Servers researched and/or installed for this Hermes Agent setup. Update when new servers are evaluated or installed.

## Evaluated (not yet installed)

### Forage (`npx forage-mcp`)
- **What**: Agent self-discovers, installs, and learns new MCP tools at runtime. `forage_search` → `forage_install` → `forage_learn`.
- **Value**: Eliminates manual MCP server discovery. Agent becomes self-extending.
- **Setup**: `mcp_servers: forage: { command: "npx", args: ["-y", "forage-mcp"] }`
- **Repo**: https://github.com/isaac-levine/forage

### OpenTabs (`npm install -g @opentabs-dev/cli`)
- **What**: AI calls web APIs through user's authenticated browser session. No API keys, no OAuth — if you're logged in, the agent can use it. 100+ plugins.
- **Value**: Access corporate portals, booking sites with no public API.
- **Requires**: Node.js 22+
- **Repo**: https://github.com/opentabs-dev/opentabs

### Anyquery
- **What**: SQL queries to 40+ data sources (GitHub, Notion, etc.) via MCP.
- **Value**: Quick analytics without scripts. Cross-service JOINs.
- **Repo**: https://github.com/julien040/anyquery

### Cortex (`github.com/gzoonet/cortex`)
- **What**: Local-first knowledge graph: watches project files, extracts decisions/patterns, answers natural language queries with citations.
- **Value**: Cross-project knowledge retrieval. Complements session_search.
- **Repo**: https://github.com/gzoonet/cortex

### PersonalizationMCP
- **What**: 90+ tools for Steam, YouTube, Bilibili, Spotify, Reddit.
- **Repo**: https://github.com/YangLiangwei/PersonalizationMCP

### Network-AI (`npx network-ai-server --port 3001`)
- **What**: Multi-agent orchestrator — shared blackboard with mutexes, FSM governance, budgets. 28 adapters incl. Hermes.
- **Value**: Parallel agent coordination with state safety.
- **Repo**: https://github.com/Jovancoding/Network-AI