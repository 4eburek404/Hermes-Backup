# Curated MCP Servers for Hermes Agent

Servers researched and verified working (or verified reachable + auto-registering) as of 2026-04.

## 1. Forage — Self-discovering MCP tool registry

- **Command**: `npx -y forage-mcp`
- **Transport**: stdio
- **GitHub**: https://github.com/isaac-levine/forage
- **What it does**: Agent can search, install, and learn new MCP tools at runtime without restart. Three operations: `forage_search` → `forage_install` → `forage_learn`. Installed tools auto-start on next session.
- **Use case**: When agent hits a task it can't solve (e.g., "query PostgreSQL"), it searches Forage, installs the right MCP server, and gains the capability instantly.

**Hermes config:**
```yaml
mcp_servers:
  forage:
    command: "npx"
    args: ["-y", "forage-mcp"]
```

---

## 2. OpenTabs — Browser-authenticated API access

- **Install**: `npm install -g @opentabs-dev/cli`
- **Transport**: stdio (via CLI)
- **GitHub**: https://github.com/opentabs-dev/opentabs
- **What it does**: Agent calls web APIs through the user's authenticated browser session. No OAuth, no API keys — if you're logged in, the agent can use it. 100+ plugins for popular services.
- **Use case**: Corporate portals, booking sites, internal tools with no public API.
- **Requires**: Node.js 22+

**Hermes config:**
```yaml
mcp_servers:
  opentabs:
    command: "opentabs"
    args: ["mcp"]
```

---

## 3. Anyquery — SQL over 40+ data sources

- **Command**: `anyquery mcp` (after install)
- **Transport**: stdio
- **GitHub**: https://github.com/julien040/anyquery
- **What it does**: SQL queries against GitHub, Notion, SQLite, and 40+ other sources via MCP. Joins across sources.
- **Use case**: Quick analytics without writing scripts.

**Hermes config:**
```yaml
mcp_servers:
  anyquery:
    command: "anyquery"
    args: ["mcp"]
```

---

## 4. Cortex — Local knowledge graph for projects

- **GitHub**: https://github.com/gzoonet/cortex
- **What it does**: Watches project files, extracts decisions/patterns/dependencies, builds a knowledge graph. Answers queries with citations. Deduplicates memory, finds contradictions.
- **Use case**: Cross-project architectural recall; complement to session_search.

(Not yet tested as MCP server — check README for transport details before configuring.)

---

## 5. Network-AI — Multi-agent orchestration

- **Command**: `npx network-ai-server --port 3001`
- **Transport**: HTTP
- **GitHub**: https://github.com/Jovancoding/Network-AI
- **What it does**: Shared blackboard with atomic locking, FSM governance, per-agent budgets, HMAC/Ed25519 audit. 28 adapters including Hermes. Agent VCR, comparison runner, approval inbox.
- **Use case**: Running parallel Hermes agents with coordinated shared state, preventing race conditions.

---

## Evaluation Criteria (for adding new servers)

When evaluating an MCP server for Hermes:
1. **Transport**: stdio or HTTP? Both work; stdio needs Node.js/uv, HTTP needs `mcp` package with streamable_http support.
2. **Auth burden**: env-var API key > auto-registering > OAuth flow. Verify auth mechanism works with Hermes before installing.
3. **Cost model**: Free tier limits, per-call pricing, payment method (x402, MPP, API key). **x402 micropayment servers are not supported by Hermes** — tools will return `payment_required` and the server will be marked unreachable.
4. **Tool count vs. signal-to-noise**: 500+ tools is only useful if discoverability is good (search, categories). Verify actual free tool count, not advertised count.
5. **Local vs. remote**: Local servers have zero latency but consume resources; remote servers may have network issues but zero local footprint.
6. **Restart requirement**: Hermes MCP has no hot-reload; adding/removing servers requires restart.