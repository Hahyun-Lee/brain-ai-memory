# Connect Brain-AI Memory through MCP

The MCP server is the shortest path from the public runtime to an existing
agent. It exposes the memory-management kernel—typed writes, scoped recall,
entity relations, exact state, and explicit handoff primitives—plus an optional
proposed-action verdict. It does not take over the model, its conversation
history, working context, or workflow engine.

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

The memory surfaces and the downstream control surface have different
contracts:

- `brain_remember`, entity/relation tools, checkpoint, consolidation preview,
  supersession, and the recall portion of `brain_context` operate on the
  memory-management kernel.
- `brain_check_action` and the optional `proposed_action` input to
  `brain_context` return a control verdict. MCP does not enforce that verdict;
  the host must consume it before executing the corresponding action.

| MCP surface | Responsibility |
|---|---|
| `brain_context` | bind an optional entity, route recall, and optionally return a proposed-action verdict |
| `brain_remember` | write an event, fact, rule, or exact state to its owned store |
| `brain_upsert_entity` | create or resolve a stable identity and aliases |
| `brain_add_relation` | add a typed edge between existing entities |
| `brain_checkpoint` | persist a handoff and list consolidation candidates |
| `brain_consolidation_preview` | inspect proposed event promotions without applying them |
| `brain_supersede` | version a stale fact while retaining the old row and source link |
| `brain_check_action` | allow, warn, or block one proposed action deterministically; optional downstream control |
| `brain-ai://status` | read runtime configuration, component counts, and latest checkpoint |
| `brain-ai://ontology` | read the validated component/channel schema |

The server intentionally omits arbitrary command execution. `brain_check_action`
decides whether an action is allowed; the host agent or workflow engine remains
responsible for executing it. Explicit fallback commands remain available from
the local `brain-ai sequence --entity ...` CLI, where the operator controls the
process boundary.

## Host-owned integration pattern

An integrating host can close the following loop; the server does not schedule
or execute it automatically:

1. Call `brain_context` with the user query and an entity when known. Include a
   proposed action only when a control decision is needed.
2. Select relevant returned records within the host's own context budget and
   inject them into its executor. Recall applies a per-component record limit,
   not a global token-safe working-context budget.
3. If an action was checked, treat `gate.allowed = false` as a stop condition,
   not advisory context.
4. Prefer exact values returned under `IPS` over model estimates, then execute
   an allowed action in the host.
5. Explicitly record selected outcomes as episodic events or update exact state,
   and create a checkpoint when a handoff is needed.
6. Review consolidation candidates locally; apply them only after approval.

This is a host integration pattern, not a shipped autonomous loop and not a
replacement for the host model's conversation history. Framework session stores
continue to own chat transcripts; the host must select what to write into
Brain-AI's differentiated operational memory. Action policy remains advisory
unless the host wires an enforcement boundary.

## Choose the integration strength honestly

| Level | What you wire | What you get |
|---|---|---|
| diagnostic | run `brain-ai tour`, `run`, and `status` manually | inspect whether the mapping fits your failures |
| advisory memory | connect MCP and call the memory tools explicitly | scoped recall candidates, exact state, explicit writes, and audit; context selection and tool use still depend on the host |
| advisory control | pass a proposed action to `brain_context` or call `brain_check_action` | a deterministic verdict that the host may consume |
| enforced control | route supported local commands through `brain-ai harness`, or make a host pre-action hook consume `brain_check_action` | a block verdict becomes a real stop condition at that wired boundary |

MCP connection alone provides tool availability, not memory use or control
enforcement. Server instructions help a client choose tools but cannot guarantee
that it calls them, selects the right records, or routes every unrelated host
tool call through the gate. A production integration must enforce this at the
host boundary.

For advisory integration, add an instruction equivalent to:

```text
For cross-session work, call brain_context with the active entity and select only
the records needed for the host context. Before a mutating action, include the
proposed action and stop if gate.allowed is false. Prefer IPS exact state over
estimates. After completing work, explicitly record selected changed state or
events and create a checkpoint when a handoff is needed.
```

## Current boundary

The `v0.3` MCP surface is local-first and single-user. It does not yet include
automatic Claude Code/Codex/provider transcript ingestion, token-budgeted
working-context assembly or injection, autonomous lifecycle scheduling,
conflict-triggered supersession, checkpoint consumption/resume, compact/split
transforms, physical archive movement or verified deletion, access control,
encryption at rest, migrations for distributed stores, concurrent-writer
coordination, or framework-specific automatic hook wiring. Those remain host
responsibilities or release gates for a production service.
