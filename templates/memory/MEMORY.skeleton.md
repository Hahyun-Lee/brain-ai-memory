# Memory

> The always-loaded index. This file is read at the start of every session, so it
> is paid for on every session and has a hard size ceiling (docs/02, "Index
> budget"). Keep it to **one line per entry**: a title, a link, and a short hook.
> Detail lives in the linked topic files, never here. When this file approaches
> its ceiling, that is the trigger to run the lifecycle (docs/02), not to raise
> the ceiling. Delete this quote block when you adopt the file.

## Index

> One line each. Format: `- [Title](topic-file.md) — one-line hook of why it matters.`
> Every topic file should be linked from here. An entry that exists but is not
> linked is an orphan: unrecallable, and a sign the store is decaying into
> write-only memory (docs/02, "Orphan rate").

- [Example topic](topics/example-topic.md) — what this entry is, in one line.

## Decisions

> Durable decisions, newest kept, superseded versions removed (docs/02, the
> `delete` operation is for things made void by a later decision). Tag the date
> and a confidence if useful. Keep the body short; link out for detail.

- `[YYYY-MM-DD]` <decision, one or two lines> → [detail](topics/some-decision.md)

## Open threads

> Work in flight. What is unfinished, and what the next step is. This is what a
> new session reloads first to reconstruct where it left off (docs/02, "Session
> start").

- <thread> — next step: <action>

---

> Maintenance: run the 7-operation pass (see `7-op-decision.md`) over this file
> on a regular cadence. The health signals to watch are index size, orphan rate,
> and per-file length against the recall cap (docs/02).
