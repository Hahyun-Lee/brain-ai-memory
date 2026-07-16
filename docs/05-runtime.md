# Installable memory-management layer and optional control bridge

The public repository includes a local-first, provider-neutral implementation
of the memory component contracts. It can adopt an existing Markdown memory,
store reviewed records by project, connect them to an MCP host, and carry a
handoff across sessions. It is not a hosted multi-tenant service and does not
collect provider transcripts automatically.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ".[mcp]"

# Run project commands against one explicit local store.
cd /path/to/your/project
export PROJECT_ROOT="$PWD"
export BRAIN_AI_HOME="$PROJECT_ROOT/.brain-ai"
brain-ai status
```

The default runtime writes only to `./.brain-ai/`:

| Path | Role |
|---|---|
| `config.json` | adapter and observer configuration |
| `events.jsonl` | append-only events written through the native runtime API |
| `state.sqlite3` | imported episodes, entities, relations, typed memory, exact state, lifecycle records, and import ledger/batches |
| `audit.jsonl` | PFC routing, gate, harness, and lifecycle traces |
| `checkpoints.jsonl` | explicit session checkpoints |
| `workflows/` | saved Markdown audits and reviews, apply receipts, locks, and host-config backups |

Set `BRAIN_AI_HOME` once as above, or put `--home` before every subcommand, to
avoid auditing one store and connecting another. The files under `.brain-ai/`
are ordinary local SQLite, JSON, and JSONL files; the package does not encrypt
them. Keep the directory private, out of source control, and backed up as
appropriate for the records it contains.

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

## Adopt an existing Markdown memory file

The adoption workflow separates observation, human judgment, and mutation:

```text
MEMORY.md -> audit -> review -> apply -> typed, entity-scoped store
                         \-> rollback (logical undo)
```

Start with an audit. The entity is required so imported records cannot leak
across project scope:

```bash
brain-ai audit "$PROJECT_ROOT/.claude/MEMORY.md" --entity Atlas
# Or omit the path to discover ./.claude/MEMORY.md, then ./MEMORY.md.
```

`audit` reads one regular UTF-8 Markdown file up to 2 MiB (100 kB per line), records source hashes and line
spans, and reports heading-informed import candidates, exact normalized
duplicates, and different literal values for the same explicit `key: value`.
It does not render Markdown, execute links or HTML, collect a transcript, infer
which statement is true, or decide which value is current. The source file and
typed memory records remain unchanged. By default only the audit plan is saved
under `.brain-ai/workflows/audits/`; use `--no-save` for a pure preview that
does not initialize the runtime. Front matter, fenced code, HTML comments, and
block quotes are inert. Default discovery refuses symlinked path components and
never searches outside the selected project root.

Inspect the generated item IDs before saving any decisions:

```bash
brain-ai review audit_0123456789abcdef
```

A review with no choice is read-only. Save only the decisions you intend to
import:

```bash
brain-ai review audit_0123456789abcdef --approve-ready
brain-ai review audit_0123456789abcdef \
  --set item_a1b2c3d4e5f60708=state \
  --set item_b1c2d3e4f5061728=episodic \
  --rule 'item_c1d2e3f405162738=deploy\s+production' --rule-effect block \
  --supersede item_d1e2f30415263748=mem_1234abcd5678
```

`--approve-ready` accepts only unambiguous semantic/episodic suggestions and
marks exact duplicate candidates as `skip`; entries marked `needs_review`
remain unresolved. Explicit `--set` actions are `semantic`, `episodic`,
`state`, or `skip`. A state decision requires an explicit key/value entry, a
rule requires an operator-supplied regular expression and effect, and
supersession requires the ID of an active semantic record. Unresolved entries
are not imported. Saving a review changes neither the Markdown source nor its
memory records. The human display shortens long entry text for terminal safety;
use `--json` or open the reported source line range before approving a truncated
item. Project-scoped supersession accepts only a fact already linked to that
same project; it cannot silently replace global or another project's memory.

Apply the saved decisions only after inspecting the review:

```bash
brain-ai apply review_0123456789abcdef --yes
# The corresponding audit ID may also be used; the latest saved review wins.
```

`apply` imports only explicit, non-`skip` decisions in one SQLite transaction,
binds them to the reviewed entity, and stores source path, line range, fragment
hash, and source hash as provenance. It never rewrites, compacts, or deletes
the source `MEMORY.md`. Applying the same completed review again is idempotent
and returns `already_applied`, even if the source later moved or changed; the
receipt then reports `source_file_changed: true` without repeating the import.

The workflow uses optimistic conflict guards. A review is tied to the audited
source SHA-256 and to a logical typed-store revision. If the Markdown changes
after audit, the store changes after review, a supersession target changes, or
a rollback would overwrite later memory work, the CLI refuses the operation
with exit status **3**. Re-run `audit` and `review` against the current state.
Ordinary usage or validation errors use exit status 2.

An applied batch can be logically undone while retaining its audit evidence:

```bash
brain-ai rollback batch_0123456789ab --yes
# A review ID such as review_0123456789abcdef is also accepted.
```

Rollback archives semantic rows created by the batch, removes entity links the
batch added to pre-existing facts, disables imported rules, marks imported
episodes rolled back, restores the previous exact state, and restores a
superseded fact when applicable. It does not alter `MEMORY.md`, erase the ledger,
or claim physical deletion. It is accepted only while the store still matches
that batch's recorded post-apply revision. If a later applied batch reuses one
of its targets without changing that revision, the dependency guard also
requires the later batch to be rolled back first.

A new audit and review may import the same source again after rollback. The
ledger keeps both the rolled-back attempt and the new active attempt.

All workflow commands support `--json` for machine-readable plans and
receipts.

## Connect a project-scoped MCP host

The connection commands preview a reviewable host-config diff by default. They
do not modify host configuration until `--apply` is present. The entity must
already exist in the same `BRAIN_AI_HOME`. A successful adoption `apply`
creates it; otherwise create it once before connecting:

```bash
brain-ai entity add --name Atlas --type project
```

Use the same project root and runtime home throughout:

```bash
brain-ai connect codex --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai connect codex --entity Atlas --project-root "$PROJECT_ROOT" --apply

brain-ai connect claude-code --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai connect claude-code --entity Atlas --project-root "$PROJECT_ROOT" --apply
```

Project scope writes a managed block to `.codex/config.toml` for Codex or a
managed `brain-ai-memory` server to `.mcp.json` for Claude Code. The generated
server command pins the current Python interpreter and absolute runtime home,
then passes `--entity Atlas`; that entity becomes the MCP server's default
scope. These paths are machine-local and should be reviewed before committing
a project config. `connect --apply` requires the
entity to exist, refuses conflicting unmanaged settings, and saves a private
backup when replacing a non-empty config. Preview output is limited to a
sanitized view of the managed `brain-ai-memory` entry; unexpected environment
data is redacted and unrelated host configuration is not echoed. Use
`brain-ai doctor --host codex --project-root "$PROJECT_ROOT"` or
`brain-ai doctor --host claude-code --project-root "$PROJECT_ROOT"` to verify
the current interpreter and runtime home; add `--entity Atlas` when the default
entity must also match.

Removal has the same preview/apply split and only removes an entry marked as
owned by this command. Run it against the same scope and project config with
the same Brain-AI home; if `--entity` is supplied, that must match too:

```bash
brain-ai disconnect codex --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai disconnect codex --entity Atlas --project-root "$PROJECT_ROOT" --apply

brain-ai disconnect claude-code --entity Atlas --project-root "$PROJECT_ROOT"
brain-ai disconnect claude-code --entity Atlas --project-root "$PROJECT_ROOT" --apply
```

A manually written MCP entry is unmanaged. `connect` will not overwrite it and
`disconnect` will not remove it; edit or remove that entry in the host config
or client that created it.

Pass `--scope user` deliberately if a user-level configuration is wanted;
project scope is the default. Connecting MCP makes tools available but does
not collect conversations, call memory tools automatically, or enforce action
verdicts. See [the MCP guide](07-mcp-server.md) for the tool contract.

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
bound memory, state, or rule from entering the bundle. Records written without
an entity are intentionally global and remain visible in every entity scope.
`brain-ai ontology`
validates and displays the component/channel schema loaded at startup.

## Project-scoped handoff and resume

The legacy `checkpoint` command remains available for a global summary. For a
handoff that cannot be confused with another project, use an existing entity:

```bash
brain-ai handoff --entity Atlas \
  --summary "Release review complete" \
  --next "Run staging verification" \
  --next "Request production approval"

brain-ai resume --entity Atlas
```

`handoff` appends an `entity-handoff` checkpoint with the summary,
`next_actions`, entity-scoped component counts, and pending consolidation
candidates. `resume` returns the newest handoff for exactly that entity; it
does not merge other projects, consume or acknowledge the checkpoint, or
reconstruct a provider transcript. Before the first handoff it returns
`status: not_found` with an empty summary and action list, rather than treating
the first session as an error. Both commands support `--json`.

When `--home` is used, printed `Next:` commands retain that absolute home so a
copy-pasted review, apply, or connection command cannot switch stores.

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
brain-ai handoff --entity Atlas --summary "release review complete"
```

These are independent calls; the order above is the recommended end-of-session
flow when promotion should be reflected in an entity-scoped handoff. A host integration must
call `brain_remember` (or `brain-ai remember`) when it selects an event to
retain, preview and apply consolidation when promotion is wanted, and call
`brain_checkpoint`/`brain-ai handoff` when an entity-scoped handoff is wanted.
The runtime neither infers those events from a provider transcript nor
schedules these calls for the host.

Supersede a stale semantic memory while preserving the old row and a source
link:

```bash
brain-ai supersede mem_old_id --text "The release window is Thursday" \
  --entity "Atlas 2.1"
```

With `--entity`, the old fact must already be bound to that entity, and only
that entity's binding is replaced. Omit `--entity` only for an intentional
global update.

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
- Markdown audit reports structural candidates only. A duplicate is literal
  normalized equality, and a possible conflict is limited to different values
  under the same explicit key. Neither is a truth or freshness judgment.
- The runtime does not automatically archive or ingest Claude Code JSONL,
  Codex rollouts, or provider transcripts, and this repository ships no adapter
  for those formats. An integrating host or custom adapter must map selected
  events into the runtime. Do not retain a raw trace without an explicit host
  privacy and retention policy; if retained, preserve it as evidence rather
  than rewriting it in place. Backup, access control, encryption, and deletion
  remain host responsibilities.
- Lifecycle commands record state and active-view decisions. They do not
  compact or split content, move archive files, consume or acknowledge
  checkpoints, or perform verified physical erasure automatically. Markdown
  adoption imports reviewed records but deliberately leaves its source file
  unchanged.
- `brain-ai harness` and `brain-ai sequence` are optional local helpers, not
  automatic host-wide enforcement. Pass `--entity` when entity-bound rules must
  apply. MCP returns action verdicts but does not intercept unrelated host tool
  calls.
- Production deployments still need their own access control, encryption,
  backups, concurrency policy, model client, and organization-specific hooks.
- `connect` and `disconnect` manage only their marked Codex/Claude project
  configuration. They do not install hooks or make the host call MCP tools.
- The MCP server is an optional install (`pip install ".[mcp]"`). See
  [the MCP guide](07-mcp-server.md).
