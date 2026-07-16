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
/absolute/path/to/brain-ai-memory/.venv/bin/python \
  -m brain_ai_memory.mcp_server \
  --home /absolute/path/to/.brain-ai --entity Atlas
```

`stdio` is the default transport. `--entity Atlas` establishes the server's
default project scope: `brain_context`, `brain_check_action`, `brain_remember`,
`brain_checkpoint`, `brain_resume`, and `brain_supersede` use it whenever a call
does not supply an entity. An explicit tool argument overrides the default.

The recommended project setup previews a host-config diff first and writes it
only with `--apply`. Create the entity before applying the connection:

```bash
brain-ai entity add --name Atlas --type project

brain-ai connect codex --entity Atlas --project-root .
brain-ai connect codex --entity Atlas --project-root . --apply

# Or use Claude Code:
brain-ai connect claude-code --entity Atlas --project-root .
brain-ai connect claude-code --entity Atlas --project-root . --apply
```

Project scope is the default. The command writes a marked managed block to
`.codex/config.toml` or a managed server entry to `.mcp.json`, pinning the
current Python interpreter, absolute Brain-AI home, and **locked project
entity**. Calls served by that project connection cannot override the entity,
so a prompt or tool call cannot silently cross into another project's memory.
These paths are machine-local and should be reviewed before committing. It refuses
conflicting unmanaged entries and backs up a non-empty config before applying a
change. A preview displays only a sanitized view of the managed
`brain-ai-memory` entry; unexpected environment data is redacted and unrelated
host configuration is not printed.

Removal also has a preview/apply split. It removes only an entry marked as
owned by this command, from the same scope and project config, and only when its
recorded Brain-AI home matches the `--home` in use. If `--entity` is supplied,
that must match too:

```bash
brain-ai disconnect codex --entity Atlas --project-root .
brain-ai disconnect codex --entity Atlas --project-root . --apply

brain-ai disconnect claude-code --entity Atlas --project-root .
brain-ai disconnect claude-code --entity Atlas --project-root . --apply
```

Use `--scope user` only when a user-level, tools-only connection is intentional.
Unlike project scope, the generated user connection uses `--entity` as an
overridable default, because one user-level server may deliberately serve more
than one entity. Autonomous loop mode remains project-only. A manual client
configuration is typically equivalent to:

```json
{
  "mcpServers": {
    "brain-ai-memory": {
      "command": "/absolute/path/to/brain-ai-memory/.venv/bin/python",
      "args": [
        "-m", "brain_ai_memory.mcp_server",
        "--home", "/absolute/path/to/.brain-ai",
        "--entity", "Atlas"
      ]
    }
  }
}
```

Use the absolute Python interpreter from the environment where the package and
MCP extra are installed, plus an absolute home path, so the host does not depend
on an activated shell and the client and CLI share the same state.

Managed project connections created before v0.6 used the same overridable
`--entity` form. `brain-ai doctor --host codex|claude-code --entity Atlas
--project-root .` reports `migration_required` and prints the exact
`brain-ai ... connect ... --apply` command that rewrites only the owned entry to
`--locked-entity`. Preview that connection command without `--apply` first when
you want to inspect the diff.

For automatic start-of-session recall and dirty-only checkpoints, add `--mode
loop` to the project connection command and follow the [autonomous loop
guide](08-autonomous-loop.md). Applying loop mode is refused before any host
configuration is changed when an applicable global or project-scoped legacy
rule is quarantined; `rule list` and `doctor` provide the remediation path.

This and the following manual or client-created entries are intentionally
**unmanaged**.
`brain-ai connect` will not overwrite them and `brain-ai disconnect` will not
remove them. Update or remove them manually in the host config or client that
created them. Use the `brain-ai connect ...` workflow above when managed,
previewable ownership is wanted.

### Codex CLI, desktop, and IDE

Codex clients share MCP configuration. Add this to `~/.codex/config.toml` or a
trusted project's `.codex/config.toml`:

```toml
[mcp_servers.brain-ai-memory]
command = "/absolute/path/to/brain-ai-memory/.venv/bin/python"
args = ["-m", "brain_ai_memory.mcp_server", "--home", "/absolute/path/to/.brain-ai", "--entity", "Atlas"]
```

The official documentation confirms support for local stdio and Streamable
HTTP servers in the desktop app, CLI, and IDE extension: [Codex MCP
documentation](https://developers.openai.com/codex/mcp).

### Claude Code

Register the local stdio server:

```bash
claude mcp add --transport stdio brain-ai-memory -- \
  /absolute/path/to/brain-ai-memory/.venv/bin/python \
  -m brain_ai_memory.mcp_server \
  --home /absolute/path/to/.brain-ai --entity Atlas
claude mcp get brain-ai-memory
```

Use `--scope project` only when you intentionally want a reviewable `.mcp.json`
shared with collaborators. Claude Code asks users to approve project-scoped
servers. See the [official Claude Code MCP
documentation](https://code.claude.com/docs/en/mcp).

For an isolated local HTTP deployment:

```bash
/absolute/path/to/brain-ai-memory/.venv/bin/python \
  -m brain_ai_memory.mcp_server \
  --transport streamable-http --host 127.0.0.1 --port 8000
```

Do not bind this alpha server to a public interface. Authentication,
multi-tenancy, and network hardening are not included.

## What the agent can call

The memory surfaces and the downstream control surface have different
contracts:

- `brain_remember`, entity/relation tools, checkpoint, consolidation preview,
  resume, supersession, and the recall portion of `brain_context` operate on
  the memory-management kernel.
- `brain_check_action` and the optional `proposed_action` input to
  `brain_context` return a control verdict. MCP does not enforce that verdict;
  the host must consume it before executing the corresponding action.

| MCP surface | Responsibility |
|---|---|
| `brain_context` | bind an optional entity, route recall, and optionally return a proposed-action verdict |
| `brain_remember` | write an event, fact, rule, or exact state to its owned store |
| `brain_upsert_entity` | create or resolve a stable identity and aliases |
| `brain_add_relation` | add a typed edge between existing entities |
| `brain_checkpoint` | with an explicit/default entity, persist a scoped handoff with `summary`, `next_actions`, scoped counts, and pending consolidation; without either, retain the legacy global checkpoint behavior |
| `brain_resume` | return the newest handoff for exactly one explicit/default entity, or `status: not_found` with empty handoff fields before the first one |
| `brain_consolidation_preview` | inspect proposed event promotions without applying them |
| `brain_supersede` | within one explicit/default entity, replace a fact already bound there while retaining the old row and source link |
| `brain_check_action` | allow, warn, or block one proposed action deterministically; optional downstream control |
| `brain-ai://status` | read runtime configuration, component counts, and latest checkpoint |
| `brain-ai://ontology` | read the validated component/channel schema |

The server intentionally omits arbitrary command execution. `brain_check_action`
decides whether an action is allowed; the host agent or workflow engine remains
responsible for executing it. Explicit fallback commands remain available from
the local `brain-ai sequence --entity ...` CLI, where the operator controls the
process boundary.

The MCP surface does not expose Markdown `audit`, `review`, `apply`, `rollback`,
or host-config editing. Those are deliberate local-operator CLI actions. In
particular, connecting a server neither scans a provider transcript nor imports
an existing `MEMORY.md`; use the explicit, hash-guarded CLI workflow documented
in [the runtime guide](05-runtime.md). A source-hash or typed-store-revision
conflict is a refused operation with CLI exit status 3, not an automatic merge.

## Host-owned tools-only integration pattern

In the default `--mode tools` connection, an integrating host can close the
following loop; the server does not schedule or execute it automatically:

1. At session start, call `brain_resume` for the active entity when a prior
   handoff may exist. Treat `status: not_found` as a normal first-run result,
   then call `brain_context` with the user query. A
   project-configured default entity may be omitted from each call; pass an
   explicit entity when intentionally overriding it. Include a proposed action
   only when a control decision is needed.
2. Select relevant returned records within the host's own context budget and
   inject them into its executor. Recall applies a per-component record limit,
   not a global token-safe working-context budget.
3. If an action was checked, treat `gate.allowed = false` as a stop condition,
   not advisory context.
4. Prefer exact values returned under `IPS` over model estimates, then execute
   an allowed action in the host.
5. Explicitly record selected outcomes as episodic events or update exact
   state. Create a scoped handoff with `brain_checkpoint(entity, summary,
   next_actions)` when another session needs to continue the work.
6. Review consolidation candidates locally; apply them only after approval.
   Supersede stale knowledge only with the active entity; the old fact must
   already be bound to that scope.

This tools-only pattern is not a replacement for the host model's conversation
history. Framework session stores continue to own chat transcripts; the host
must select what to write into Brain-AI's differentiated operational memory.
Action policy remains advisory unless the host wires an enforcement boundary.
The separate project-only `--mode loop` integration automates bounded recall,
selected artifact-event capture, and dirty-only checkpoints; it still does not
store raw transcripts or infer durable truth from model output.

`brain_resume` reads the newest scoped handoff; before the first handoff it
returns `status: not_found`, an empty summary, and an empty `next_actions` list.
It does not consume or acknowledge a handoff, merge several entities, or
reconstruct a conversation. Likewise, the server does not infer truth or
currentness from conflicting prose. The host must make an explicit write or an
entity-scoped supersession decision. MCP supersession requires an explicit or
configured default entity and cannot deactivate global or another entity's
memory.

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
the records needed for the host context; first call brain_resume when a previous
handoff may exist. Before a mutating action, include the proposed action and stop
if gate.allowed is false. Prefer IPS exact state over estimates. After completing
work, explicitly record selected changed state or events and create an
entity-scoped checkpoint with next_actions when a handoff is needed.
```

## Current boundary

The public MCP surface is local-first and single-user. The project connection
command writes only host MCP configuration; it does not install hooks or force
the host to call a tool. The server does not include automatic Claude
Code/Codex/provider transcript ingestion, token-budgeted working-context
assembly or injection, autonomous lifecycle scheduling, truth inference or
conflict-triggered supersession, checkpoint consume/acknowledge semantics,
compact/split transforms, physical archive movement or verified deletion,
access control, encryption at rest, migrations for distributed stores, or
distributed-writer coordination. Those remain host responsibilities or release
gates for a production service.
