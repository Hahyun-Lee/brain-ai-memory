#!/usr/bin/env python3
"""
Deterministic capacity simulation for two memory-index representations.

THE CLAIM (narrow, on purpose)
    An agent recalls memory under a budget: only the first N characters of the
    always-loaded index reach the agent at query time (docs/02, "Index budget").
    Two memory policies are compared on identical data, queries, and budget:

      append-only : every session appends the full entry (summary + detail) to
                    the index. The naive default docs/02 describes: nothing is
                    ever compacted, so the index grows without bound.
      lifecycle   : the index holds one line per entry (a pointer); detail lives
                    in a separate topic file loaded on demand. This is the
                    discipline from docs/02 and templates/memory/.

    Prediction: once cumulative memory exceeds the budget, append-only silently
    evicts the oldest entries, so queries about old-but-needed facts start
    failing. The lifecycle policy packs pointers instead of full detail, so far
    more entries stay reachable, and it answers from the pointed-to topic file.

FALSIFIER AND CONTROL
    - The same BUDGET is applied to both policies. The lifecycle index is
      truncated by the exact same rule as the append-only index.
    - Same entries, same queries, same value lookup predicate.
    - The only difference is what each policy puts in the always-loaded index.
    - The sweep includes the region where everything fits under budget. There,
      both policies score 100% and there is NO difference. The advantage appears
      only when, and because, cumulative memory exceeds the budget, which the
      output states explicitly. If you enlarge BUDGET or shrink the entries so
      nothing overflows, the difference disappears. That is the falsifier.
    - The lifecycle policy has its OWN ceiling (its one-line index can overflow
      too); the sweep runs long enough to show it. The discipline raises the
      ceiling; it does not make it infinite.

WHAT THIS DOES AND DOES NOT SHOW
    It shows a storage-budget mechanism in a reproducible artifact. It is not a
    benchmark: retrieval is exact substring lookup over synthetic entries, not a
    language model reading ambiguous history. It does not establish gains in
    semantic retrieval, reasoning, latency, cost, or real-agent performance. See
    evidence/README.md and benchmarks/README.md.

Run:
    python3 evidence/lifecycle_under_budget.py
"""

# --- Parameters. Change these and the result moves; that is the point. --------
BUDGET = 800          # chars of the always-loaded index available at query time
DETAIL_CHARS = 200    # size of a full entry's detail body (append-only pays this)
MAX_SESSIONS = 24     # how far to grow memory in the sweep
PER_FILE_CAP = 500    # per-file recall cap for an on-demand topic file (docs/02)
# ------------------------------------------------------------------------------


def one_liner(i):
    """The lifecycle index line for entry i: a pointer, no detail."""
    return f"[s{i:02d}] K{i}: one-line hook -> topic/K{i}.md\n"


def full_entry(i):
    """The append-only index block for entry i: summary plus full detail."""
    value_marker = f"value:[V{i}]"   # bracketed so [V1] cannot match inside [V12]
    pad = "." * max(0, DETAIL_CHARS - len(value_marker))
    return one_liner(i) + f"  detail: {pad}{value_marker}\n"


def topic_file(i):
    """The on-demand detail file the lifecycle pointer resolves to."""
    body = f"Topic for K{i}.\nvalue:[V{i}]\n" + ("." * 80)
    return body[:PER_FILE_CAP]


def append_only_can_answer(key_i, n):
    """True if V{key_i} survives in the budget-truncated append-only index."""
    index = "".join(full_entry(i) for i in range(1, n + 1))
    recalled = index[-BUDGET:]              # budget keeps the most-recent tail;
    return f"value:[V{key_i}]" in recalled  # the oldest entries fall off the front


def lifecycle_can_answer(key_i, n):
    """True if K{key_i}'s pointer survives the budget, then its topic resolves."""
    index = "".join(one_liner(i) for i in range(1, n + 1))
    recalled = index[-BUDGET:]            # same truncation rule as append-only
    if f"topic/K{key_i}.md" not in recalled:
        return False                      # pointer evicted: same budget rule
    return f"value:[V{key_i}]" in topic_file(key_i)


def accuracy(policy_fn, n):
    """Query every fact ever stored (K1..Kn); fraction answered correctly."""
    answered = sum(policy_fn(k, n) for k in range(1, n + 1))
    return answered / n


def first_drop(policy_fn):
    """First session count at which the policy falls below 100% accuracy."""
    for n in range(1, MAX_SESSIONS + 1):
        if accuracy(policy_fn, n) < 1.0:
            return n
    return None


def main():
    print("Capacity simulation (exact-string lookup; not an LLM benchmark)")
    print(f"Budget = {BUDGET} chars/index   detail = {DETAIL_CHARS} chars/entry")
    print(f"append-only pays ~{len(full_entry(1))} chars/entry in the index; "
          f"lifecycle pays ~{len(one_liner(1))}.\n")
    print(f"{'sessions':>8} | {'append-only recall':>18} | {'lifecycle recall':>16} | note")
    print("-" * 64)
    for n in range(1, MAX_SESSIONS + 1):
        a = accuracy(append_only_can_answer, n)
        l = accuracy(lifecycle_can_answer, n)
        note = "" if a == l else "append-only evicting old facts"
        if a == l == 1.0:
            note = "both fit under budget (no difference)"
        print(f"{n:>8} | {a:>18.0%} | {l:>16.0%} | {note}")

    ao = first_drop(append_only_can_answer)
    lc = first_drop(lifecycle_can_answer)
    print("\nFirst session count below 100% recall of all stored facts:")
    print(f"  append-only : {ao}")
    print(f"  lifecycle   : {lc if lc is not None else f'> {MAX_SESSIONS} (no drop in this sweep)'}")
    if ao is not None and (lc is None or lc > ao):
        factor = (lc / ao) if lc else None
        tail = f" ({factor:.0f}x higher ceiling)" if factor else " (no drop observed)"
        print(f"\nThe lifecycle index holds more before it overflows{tail}.")
    print("Enlarge BUDGET or shrink DETAIL_CHARS until nothing overflows and the\n"
          "difference vanishes: that is the simulation's own falsifier.")


if __name__ == "__main__":
    main()
