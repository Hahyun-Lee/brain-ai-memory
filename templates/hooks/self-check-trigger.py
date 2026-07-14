#!/usr/bin/env python3
"""
self-check-trigger — an advisory self-monitoring trigger (Tier 2 / Tier 3).

WHAT THIS IS
    A skeleton for the guarded and advisory tiers in docs/03-governance-tiers.md.
    Unlike behavioral-guard, it never blocks. It watches for a situation where
    the agent is about to do something error-prone and surfaces a short reminder
    of the relevant discipline, leaving the decision to the agent.

    This is how a Tier 3 principle (docs/04) gets a nudge at the moment it
    matters, instead of relying on the agent to recall it unprompted.

THE CONTRACT (adapt to your agent harness)
    - The harness invokes this before (or after) a relevant step, passing the
      step as JSON on stdin.
    - This script ALWAYS exits 0. It is advisory, not enforcing.
    - The reminder is written to stderr (or wherever your harness routes
      hook output back to the agent).

    Event schema used here, minimal and adaptable:
        {"action": "<command or content>", "context": "<optional free text>"}

WHY ADVISORY AND NOT ENFORCED
    These triggers cover judgment, not fixed rules. You cannot hard-block "you
    might be comparing two numbers that are not comparable"; you can only raise
    the question at the right moment. Blocking judgment produces false positives
    that train the agent to route around the guard (docs/03). The right strength
    is a visible reminder plus a record of how often it fires, which is the
    evidence that decides whether a pattern ever earns promotion to Tier 1.

HOW TO USE
    1. Replace TRIGGERS with the situations and reminders relevant to your work.
    2. Register as an advisory hook in your harness.
    3. Run `python3 self-check-trigger.py --selftest`.
"""

import json
import re
import sys

# --- Replace these. Each trigger pairs a matcher with the discipline to recall.
# Keep reminders to one line. A reminder the agent will not read is dead weight.
TRIGGERS = [
    (re.compile(r"\b(\d+(\.\d+)?)\s*(x|times|vs\.?|compared to)\b", re.I),
     "comparison-integrity: same data, metric, aggregation, space? "
     "If any differ, state the difference and compare only within its limits."),
    (re.compile(r"\b(all|every|none|always|never|100%|guarantee[ds]?)\b", re.I),
     "absolute claim: is there a single counterexample? If so, soften it."),
    (re.compile(r"\b(done|complete|finished|verified|works)\b", re.I),
     "self-verdict: before declaring done, one pass for stale / contradiction / "
     "overstated causation / a 'good enough' that stops short of the task."),
]
# ------------------------------------------------------------------------------

ALWAYS_EXIT = 0


def inspectable_text(event):
    """Adapt to your harness event shape; returns the text to scan."""
    if not isinstance(event, dict):
        return ""
    return " ".join(str(event.get(k, "")) for k in ("action", "context"))


def reminders_for(text):
    """Pure function: return the list of reminders this text trips.

    Importable so examples/ and tests can call it without stdin plumbing.
    """
    out = []
    for pattern, reminder in TRIGGERS:
        if pattern.search(text):
            out.append(reminder)
    return out


def _read_event():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _selftest():
    cases = [
        ("model A is 3x faster than model B", 1),
        ("this works on all inputs", 2),   # 'all' + 'works'
        ("the migration is done", 1),
        ("just listing the files", 0),
    ]
    failures = 0
    for text, expected_count in cases:
        hits = reminders_for(text)
        ok = (len(hits) == expected_count)
        failures += 0 if ok else 1
        verdict = "PASS" if ok else "FAIL"
        print(f"[{verdict}] fired={len(hits)} (expected {expected_count})  {text!r}")
        for h in hits:
            print(f"         - {h}")
    print(f"\n{len(cases) - failures}/{len(cases)} cases passed")
    return 1 if failures else 0


def main(argv):
    if "--selftest" in argv:
        return _selftest()

    event = _read_event()
    hits = reminders_for(inspectable_text(event))
    for reminder in hits:
        sys.stderr.write(f"self-check: {reminder}\n")
    return ALWAYS_EXIT


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
