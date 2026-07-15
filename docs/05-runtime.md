# Installable reference runtime

The public repository includes a local-first reference implementation of the
component contracts. It is intentionally small and provider-neutral. It is
usable code, but still an alpha reference rather than a hosted multi-tenant
service.

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

## The complete local loop

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

Route and recall an auditable context bundle for any model or agent client:

```bash
brain-ai run "What changed recently and how many reviews remain?" \
  --entity "Atlas 2.1" --action "deploy production"
```

The output names the chosen components, retrieved records, gate decision, and
latency. The runtime does not hide a model call: an application can pass this
JSON bundle to Claude, Codex, OpenAI, a local model, or a deterministic worker.
The entity scope prevents another project's identically named state or rule
from entering the bundle. `brain-ai ontology` validates and displays the
component/channel schema loaded at startup.

Run an explicit command through the TH/BG gate and CB harness:

```bash
brain-ai harness --query "verify package" -- python -m unittest discover -s tests
```

Run deterministic fallbacks until one succeeds:

```bash
brain-ai sequence --query "verify" \
  --step '["python", "missing_check.py"]' \
  --step '["python", "-m", "unittest", "discover", "-s", "tests"]'
```

The sequence is code-owned: failure of the first step cannot silently end the
procedure before the registered fallback is tried.

## Consolidation, reconsolidation, and lifecycle

Consolidation previews candidates by default and mutates state only with an
explicit apply flag:

```bash
brain-ai checkpoint --summary "release review complete"
brain-ai consolidate
brain-ai consolidate --apply
```

Reconsolidate a stale semantic memory while preserving its provenance:

```bash
brain-ai supersede mem_old_id --text "The release window is Thursday"
```

Apply one of the seven lifecycle operations:

```bash
brain-ai lifecycle episodic evt_old_id archive --reason "resolved and captured downstream"
```

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

## Boundaries

- The default BM25 adapter is a transparent local fallback, not a claim of
  embedding parity.
- The reference observer has no authentication and binds to localhost by
  default. Do not expose it directly to a network.
- Consolidation does not ask a model to invent rules. Rule promotion requires
  an explicit regular-expression pattern and human apply action.
- Production deployments still need their own access control, encryption,
  backups, concurrency policy, model client, and organization-specific hooks.
- The MCP server is an optional install (`pip install ".[mcp]"`). See
  [the MCP guide](07-mcp-server.md).
