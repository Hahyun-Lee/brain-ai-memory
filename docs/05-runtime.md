# Installable memory kernel and optional control bridge

The public repository includes a local-first reference implementation of the
component contracts. It is intentionally small and provider-neutral. It is
usable code, but still an alpha reference kernel rather than a drop-in agent
memory service or a hosted multi-tenant system.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

brain-ai tour
brain-ai status
```

The default runtime writes only to `./.brain-ai/`:

| Path | Role |
|---|---|
| `config.json` | adapter and observer configuration |
| `events.jsonl` | append-only episodic memory (HC) |
| `state.sqlite3` | entities, relations, semantic memory, rules, exact state, lifecycle records |
| `audit.jsonl` | PFC routing, gate, harness, and lifecycle traces |
| `checkpoints.jsonl` | explicit session checkpoints |

Set `BRAIN_AI_HOME` or pass `--home` to use another directory.

## What the package owns

| Boundary | Implemented responsibility |
|---|---|
| memory-management kernel | explicit writes for episodes, knowledge, procedural rules, and exact state; entity/relationship bindings; component-scoped recall candidates; lifecycle decision records; promotion preview/apply; supersession; checkpoints; and audit |
| optional downstream control bridge | a deterministic verdict over an explicit proposed-action string, plus local CLI command and fallback harnesses that consume that verdict |
| integrating host | select events from sessions, assemble and inject model context within its own token budget, schedule lifecycle calls, encode selected outcomes as events or state, enforce MCP verdicts, and perform retention or physical deletion |

The memory kernel does not require Brain-AI to execute commands. Conversely, a
gate verdict returned through `run` or MCP is not enforcement until the host or
the bundled CLI harness consumes it. Storing and recalling a procedural rule is
kernel behavior; using it to stop an executor belongs to the control bridge.

## Memory-kernel workflow

Write memories to the store that owns their failure mode:

```bash
brain-ai entity add --name Atlas --type project --alias A
brain-ai entity add --name "Atlas 2.1" --type release
brain-ai relation add "Atlas 2.1" belongs_to Atlas
brain-ai remember --type episodic --entity "Atlas 2.1" \
  --text "The release window moved to Thursday" --promote semantic
brain-ai remember --type semantic --entity "Atlas 2.1" \
  --text "Production releases require review"
brain-ai remember --type state --entity "Atlas 2.1" --key open_reviews --value 3
brain-ai remember --type rule --entity "Atlas 2.1" \
  --pattern 'deploy\s+production' --text "approval required"
```

Route and recall an auditable candidate bundle for any model or agent client:

```bash
brain-ai run "What changed recently and how many reviews remain?" \
  --entity "Atlas 2.1" --action "deploy production"
```

The output names the chosen components, retrieved records, proposed-action
verdict, and latency. The runtime does not hide a model call: an application can
select from this JSON bundle and pass the selected records to Claude, Codex,
OpenAI, a local model, or a deterministic worker. Recall applies a per-component
record limit; it is not a global token-safe working-context assembler and does
not inject anything into a model. The entity scope prevents another project's
identically named local state or rule from entering the bundle. `brain-ai ontology`
validates and displays the component/channel schema loaded at startup.

## Optional downstream control bridge

Run an explicit local command through the proposed-action gate and command
harness:

```bash
brain-ai harness --query "verify package" --entity "Atlas 2.1" -- \
  python -m unittest discover -s tests
```

Run deterministic fallbacks until one succeeds:

```bash
brain-ai sequence --query "verify" --entity "Atlas 2.1" \
  --step '["python", "missing_check.py"]' \
  --step '["python", "-m", "unittest", "discover", "-s", "tests"]'
```

The sequence is code-owned: failure of the first step cannot silently end the
procedure before the supplied fallback is tried.

These CLI commands own only the subprocesses they start. They do not install
Claude Code or Codex hooks and do not intercept other host tools. Both commands
accept `--entity` and apply matching entity-bound rules to every attempted
command. When `--entity` is omitted, entity-bound rules are deliberately out of
scope; an integrating host must therefore pass the active entity rather than
rely on a name hidden inside command text.

## Consolidation, supersession, and lifecycle primitives

Consolidation previews candidates by default and mutates state only with an
explicit apply flag:

```bash
brain-ai consolidate
brain-ai consolidate --apply
brain-ai checkpoint --summary "release review complete"
```

These are independent calls; the order above is the recommended end-of-session
flow when promotion should be reflected in the handoff. A host integration must
call `brain_remember` (or `brain-ai remember`) when it selects an event to
retain, preview and apply consolidation when promotion is wanted, and call
`brain_checkpoint` (or `brain-ai checkpoint`) when a handoff is wanted. The
runtime neither infers those events from a provider transcript nor schedules
these calls for the host.

Supersede a stale semantic memory while preserving the old row and a source
link:

```bash
brain-ai supersede mem_old_id --text "The release window is Thursday"
```

Record one of the seven lifecycle decisions and update its active-view status:

```bash
brain-ai lifecycle episodic evt_old_id archive --reason "resolved and captured downstream"
```

This command is soft-state management, not a physical file transformation.
For episodic entries, archive/delete/migration decisions hide the source from
default active views while preserving the append-only event; semantic
archive/delete changes status while retaining the row. Compact and split only
record work for the host. Derive knowledge/rules through consolidation, and use
a separate host retention workflow for verified physical erasure.

## Programmatic use

```python
from brain_ai_memory import BrainAIRuntime

runtime = BrainAIRuntime(".brain-ai")
bundle = runtime.process(
    "What changed in the recent release plan?",
    proposed_action="deploy production",
    entity="Atlas 2.1",
)
if bundle["gate"]["allowed"]:
    context_for_your_executor = bundle["memory"]
```

The LLM remains a replaceable executor. Durable cognition lives in the stores,
rules, harness steps, checkpoints, and audit trail.

The host must still choose which returned records fit its context budget and
must explicitly execute, record outcomes, and resume from checkpoints. The
reference runtime does not manage the model's live working context.

## Boundaries

- The default BM25 adapter is a transparent local fallback, not a claim of
  embedding parity.
- Recall applies a per-component record limit. It does not guarantee a global
  token or byte budget, perform autonomous paging, or inject working context
  into a model.
- The reference observer has no authentication and binds to localhost by
  default. `/api/health` is process liveness, while status and event endpoints
  expose counts and recent audit records; they are not a lifecycle-health or
  alerting engine. Do not expose the observer directly to a network.
- Consolidation does not ask a model to invent rules. Rule promotion requires
  an explicit regular-expression pattern and an operator-provided apply flag.
- The runtime does not automatically archive or ingest Claude Code JSONL,
  Codex rollouts, or provider transcripts, and this repository ships no adapter
  for those formats. An integrating host or custom adapter must map selected
  events into the runtime. Do not retain a raw trace without an explicit host
  privacy and retention policy; if retained, preserve it as evidence rather
  than rewriting it in place. Backup, access control, encryption, and deletion
  remain host responsibilities.
- Lifecycle commands record state and active-view decisions. They do not
  compact or split content, move archive files, detect retrieval conflicts,
  consume checkpoints, or perform verified physical erasure automatically.
- `brain-ai harness` and `brain-ai sequence` are optional local helpers, not
  automatic host-wide enforcement. Pass `--entity` when entity-bound rules must
  apply. MCP returns action verdicts but does not intercept unrelated host tool
  calls.
- Production deployments still need their own access control, encryption,
  backups, concurrency policy, model client, and organization-specific hooks.
- The MCP server is an optional install (`pip install ".[mcp]"`). See
  [the MCP guide](07-mcp-server.md).
