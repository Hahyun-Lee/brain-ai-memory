# Templates

Generic, copy-paste skeletons for the constructs described in `docs/`. They are
starting points, not a framework: take one, adapt the placeholders to your stack,
and delete what you do not need. The hook skeletons depend only on the Python 3
standard library and run standalone.

## What's here

| Path | What it is | Doc it implements |
|---|---|---|
| `hooks/behavioral-guard.py` | Enforced (Tier 1) blacklist valve: blocks a denied action before it runs | [`docs/03`](../docs/03-governance-tiers.md), the BG component in [`docs/01`](../docs/01-the-mapping.md) |
| `hooks/self-check-trigger.py` | Advisory (Tier 2/3) trigger: surfaces a reminder at an error-prone moment, never blocks | [`docs/03`](../docs/03-governance-tiers.md), [`docs/04`](../docs/04-principles.md) |
| `rules/rule-stub.md` | The shape a conditional procedural rule takes (condition / principle / procedure / failure mode / tier) | [`docs/03`](../docs/03-governance-tiers.md) |
| `memory/MEMORY.skeleton.md` | The always-loaded memory index: one line per entry, detail linked out | [`docs/02`](../docs/02-memory-lifecycle.md) |
| `memory/7-op-decision.md` | Pocket version of the 7-operation lifecycle decision | [`docs/02`](../docs/02-memory-lifecycle.md) |

Copy the entire `templates/memory/` directory so the skeleton's example topic
links remain valid, then rename `MEMORY.skeleton.md` to `MEMORY.md` in the copy.

## Adapting the hooks

Both hooks share one contract, kept deliberately minimal so it maps onto most
agent harnesses:

- The harness invokes the script around a step, passing the step as JSON on stdin.
- `behavioral-guard.py` exits `0` to allow or `2` to block (block message on
  stderr, shown back to the agent). `self-check-trigger.py` always exits `0`.
- One function near the top of each file (`extract_action` / `inspectable_text`)
  reads your harness's event shape. Adapt that function; the rest is
  harness-independent.

The two `DENIED_PATTERNS` / `TRIGGERS` lists are illustrative placeholders.
Replace them with your own, and promote a pattern from advisory to enforced only
on evidence that the softer tier failed (the promotion criteria in
[`docs/03`](../docs/03-governance-tiers.md)).

## Checking they run

```
python3 templates/hooks/behavioral-guard.py --selftest
python3 templates/hooks/self-check-trigger.py --selftest
```

Worked examples that use these templates live in [`../examples/`](../examples/).
