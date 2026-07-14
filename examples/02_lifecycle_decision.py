#!/usr/bin/env python3
"""
Worked example: the 7-operation memory lifecycle decision.

Takes a few synthetic memory entries (no real data) and applies the priority
ordering from docs/02-memory-lifecycle.md to recommend exactly one operation for
each. This is the decision in templates/memory/7-op-decision.md, made executable
so you can see the ordering actually resolve conflicts.

The ordering is the whole point: a reusable lesson is promoted (migrate) before
it can be buried (archive), and "no longer relevant" never reaches delete.

Run:
    python3 examples/02_lifecycle_decision.py
"""

# Synthetic entries. Each carries the signals the decision rule reads. These are
# made up for the example; a real system would derive them from the entry's
# metadata, links, and age.
ENTRIES = [
    {
        "title": "project index", "is_anchor": True, "active": False,
        "wrong": False, "reusable": None, "covers_many_topics": False,
        "resolved_and_old": False, "partly_stale": False,
    },
    {
        "title": "current migration, outcome unknown", "is_anchor": False,
        "active": True, "wrong": False, "reusable": None,
        "covers_many_topics": False, "resolved_and_old": False,
        "partly_stale": False,
    },
    {
        "title": "grab-bag note spanning four unrelated topics",
        "is_anchor": False, "active": False, "wrong": False, "reusable": None,
        "covers_many_topics": True, "resolved_and_old": False,
        "partly_stale": False,
    },
    {
        "title": "decision later reversed and made void", "is_anchor": False,
        "active": False, "wrong": True, "reusable": None,
        "covers_many_topics": False, "resolved_and_old": True,
        "partly_stale": False,
    },
    {
        "title": "a reusable method worth keeping forever", "is_anchor": False,
        "active": False, "wrong": False, "reusable": "principle",
        "covers_many_topics": False, "resolved_and_old": True,
        "partly_stale": False,
    },
    {
        "title": "a repeatable procedure, now formalizable", "is_anchor": False,
        "active": False, "wrong": False, "reusable": "procedure",
        "covers_many_topics": False, "resolved_and_old": True,
        "partly_stale": False,
    },
    {
        "title": "resolved long ago, already in a commit", "is_anchor": False,
        "active": False, "wrong": False, "reusable": None,
        "covers_many_topics": False, "resolved_and_old": True,
        "partly_stale": False,
    },
    {
        "title": "mostly stale, one line still useful", "is_anchor": False,
        "active": False, "wrong": False, "reusable": None,
        "covers_many_topics": False, "resolved_and_old": False,
        "partly_stale": True,
    },
]


def decide(e):
    """Return (operation, why), walking the priority order top to bottom.

    Mirrors docs/02 step ordering exactly. Stop at the first match.
    """
    # 1. KEEP
    if e["is_anchor"] or e["active"]:
        return "keep", "index anchor or still active"
    if not any((e["wrong"], e["reusable"], e["covers_many_topics"],
                e["resolved_and_old"], e["partly_stale"])):
        return "keep", "no signal it has been superseded"
    # 2. SPLIT
    if e["covers_many_topics"]:
        return "split", "covers several distinct topics"
    # 3. DELETE (only if actually wrong)
    if e["wrong"]:
        return "delete", "wrong / made void by a later decision"
    # 4. MIGRATE-TO-KNOWLEDGE-BASE
    if e["reusable"] == "principle":
        return "migrate-to-knowledge-base", "reusable principle or method"
    # 5. MIGRATE-TO-RULES
    if e["reusable"] == "procedure":
        return "migrate-to-rules", "repeatable procedure, formalizable"
    # 6. ARCHIVE
    if e["resolved_and_old"]:
        return "archive", "resolved, old, captured downstream"
    # 7. COMPACT
    if e["partly_stale"]:
        return "compact", "only part has lost value"
    return "keep", "fallthrough"


def main():
    print("Applying the 7-operation decision (first match wins):\n")
    width = max(len(decide(e)[0]) for e in ENTRIES)
    for e in ENTRIES:
        op, why = decide(e)
        print(f"  {op:<{width}}  {e['title']}")
        print(f"  {'':<{width}}    why: {why}")
    print("\nNote: the 'reversed decision' is the only DELETE; the 'resolved "
          "long ago' entry\nis ARCHIVE, not DELETE. 'No longer relevant' never "
          "reaches delete.")


if __name__ == "__main__":
    main()
