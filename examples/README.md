# Examples

Tiny, runnable worked cases. Each is a single file, depends only on the Python 3
standard library, and uses no real data. They exist to make the ideas in `docs/`
concrete: you can read the doc, then run the example and watch the rule resolve.

## Running them

No setup, no install. From the repo root:

```
python3 examples/01_guard_in_action.py
python3 examples/02_lifecycle_decision.py
```

(Any Python 3.7+ works.)

## What each one shows

- **`01_guard_in_action.py`** — feeds a handful of proposed tool calls (strings
  only; nothing executes) through the enforced guard in
  `../templates/hooks/behavioral-guard.py`, and prints which are allowed and
  which are blocked and why. Demonstrates the basal-ganglia / Tier 1 valve from
  [`docs/01`](../docs/01-the-mapping.md) and [`docs/03`](../docs/03-governance-tiers.md),
  and that the guard template is reusable as a library, not only as a hook.

- **`02_lifecycle_decision.py`** — applies the 7-operation priority ordering from
  [`docs/02`](../docs/02-memory-lifecycle.md) to a set of synthetic memory
  entries and recommends one operation for each. Demonstrates why the ordering
  matters: a reusable lesson is promoted before it can be archived into silence,
  and "no longer relevant" never reaches `delete`.

## Verifying the templates standalone

The hook templates also self-test without any harness:

```
python3 templates/hooks/behavioral-guard.py --selftest
python3 templates/hooks/self-check-trigger.py --selftest
```
