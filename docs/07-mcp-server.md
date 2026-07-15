# Connect Brain-AI Memory through MCP

The MCP server is the shortest path from the public runtime to an existing
agent. It exposes typed context, deterministic action checks, memory writes,
entity relations, and lifecycle handoffs without taking over the model or its
workflow engine.

## Install and start

From a checkout:

```bash
python -m pip install ".[mcp]"
brain-ai-mcp --home /absolute/path/to/.brain-ai
```

`stdio` is the default transport. A client configuration is typically
equivalent to:

```json
{
  "mcpServers": {
    "brain-ai-memory": {
      "command": "brain-ai-mcp",
      "args": ["--home", "/absolute/path/to/.brain-ai"]
    }
  }
}
```

Use an absolute home path so the client and CLI share the same state.

### Codex CLI, desktop, and IDE

Codex clients share MCP configuration. Add this to `~/.codex/config.toml` or a
trusted project's `.codex/config.toml`:

```toml
[mcp_servers.brain_ai_memory]
command = "brain-ai-mcp"
args = ["--home", "/absolute/path/to/.brain-ai"]
```

The official documentation confirms support for local stdio and Streamable
HTTP servers in the desktop app, CLI, and IDE extension: [Codex MCP
documentation](https://developers.openai.com/codex/mcp).

### Claude Code

Register the local stdio server:

```bash
claude mcp add --transport stdio brain-ai-memory -- \
  brain-ai-mcp --home /absolute/path/to/.brain-ai
claude mcp get brain-ai-memory
```

Use `--scope project` only when you intentionally want a reviewable `.mcp.json`
shared with collaborators. Claude Code asks users to approve project-scoped
servers. See the [official Claude Code MCP
documentation](https://code.claude.com/docs/en/mcp).

For an isolated local HTTP deployment:

```bash
brain-ai-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Do not bind this alpha server to a public interface. Authentication,
multi-tenancy, and network hardening are not included.

## What the agent can call

| MCP surface | Responsibility |
|---|---|
| `brain_context` | bind an optional entity, route recall, and return an action verdict |
| `brain_check_action` | allow, warn, or block one proposed action deterministically |
| `brain_remember` | write an event, fact, rule, or exact state to its owned store |
| `brain_upsert_entity` | create or resolve a stable identity and aliases |
| `brain_add_relation` | add a typed edge between existing entities |
| `brain_checkpoint` | persist a handoff and list consolidation candidates |
| `brain_consolidation_preview` | inspect proposed event promotions without applying them |
| `brain_supersede` | version a stale fact while retaining provenance |
| `brain-ai://status` | read runtime health and component counts |
| `brain-ai://ontology` | read the validated component/channel schema |

The server intentionally omits arbitrary command execution. `brain_check_action`
decides whether an action is allowed; the host agent or workflow engine remains
responsible for executing it. Explicit fallback commands remain available from
the local `brain-ai sequence` CLI, where the operator controls the process
boundary.

## Recommended host-agent loop

1. Call `brain_context` with the user query, the intended action, and an entity
   when known.
2. Treat `gate.allowed = false` as a stop condition—not advisory context.
3. Prefer exact values returned under `IPS` over model estimates.
4. Execute the allowed action in the host agent.
5. Record a new event or exact state and call `brain_checkpoint`.
6. Review consolidation candidates locally; apply them only after approval.

This is a control protocol, not a replacement for the host model's conversation
history. Framework session stores can continue to own chat transcripts while
Brain-AI owns differentiated operational memory and action policy.

## Choose the integration strength honestly

| Level | What you wire | What you get |
|---|---|---|
| diagnostic | run `brain-ai tour`, `run`, and `status` manually | inspect whether the mapping fits your failures |
| advisory agent memory | connect MCP and instruct the agent to call `brain_context` | scoped context, exact state, audit, and deterministic verdicts; tool use still depends on the host loop |
| enforced control | route mutations through `brain-ai harness` or make a host pre-action hook consume `brain_check_action` | a block verdict becomes a real stop condition |

MCP connection alone is the second level, not the third. Server instructions
help a client choose tools but cannot guarantee that every unrelated host tool
call passes through the gate. A production integration must enforce this at the
host boundary.

For advisory integration, add an instruction equivalent to:

```text
Before any cross-session or mutating action, call brain_context with the active
entity and proposed action. If gate.allowed is false, stop. Prefer IPS exact
state over estimates. After completing work, record changed state and create a
checkpoint.
```

## Current boundary

The `v0.3` MCP surface is local-first and single-user. It does not yet include
access control, encryption at rest, migrations for distributed stores,
concurrent-writer coordination, or framework-specific automatic hook wiring.
Those remain release gates for a production service.
