# Release and operating boundary

The companion and quickstart target the published
[v0.7.0 release](https://github.com/Hahyun-Lee/brain-ai-memory/releases/tag/v0.7.0)
and [PyPI package](https://pypi.org/project/brain-ai-memory/0.7.0/).

## Choose the implementation your instructions describe

| Installation | Available scope |
|---|---|
| Published v0.7.0 | Project-scoped memory, reviewed Markdown import, supersession, exact state, source-freshness checks in the optional loop, and checkpoint/resume. |
| Post-release public source | Additional runtime fixes are source changes, not a new PyPI release. Use the package's tagged source to check v0.7.0 behavior. |
| Local development | New capture/scope/recall guidance, selected status projections and explicit cue delivery are not in the v0.7.0 wheel. |
| Private operating system | Governance, research-administration workflows, private stores and service integrations are separate from this package. |

Package metadata alone is not a feature inventory. Installing a development
checkout whose version field still says `0.7.0` can produce different behavior
from the published wheel. The companion pins the published package for a new
installation and preserves an existing configured runtime.

## v0.7.0 integration details

- A project connection created by `setup` or `connect` uses a locked entity.
  Omit the tool's `entity` argument on that connection; a task's display name
  is not a new entity identifier.
- The released server has no `brain_scope` tool. Use the configured project
  binding and returned records to inspect scope.
- Exact-state recall is selected by numeric query hints. For a known key,
  `metric KEY` selects the state route, including for textual values. Inspect
  the matching entry in `memory.IPS`.
- MCP reads do not capture new facts. `brain_remember`, explicit correction
  and a handoff are distinct operations. The [companion](../skills/brain-ai-memory/SKILL.md)
  specifies the supported routine.
- Tools mode relies on the host to call the tools. Optional hooks have their
  own event, approval and source-review boundaries in the
  [session-loop guide](08-autonomous-loop.md).

The released [MCP server](https://github.com/Hahyun-Lee/brain-ai-memory/blob/v0.7.0/src/brain_ai_memory/mcp_server.py),
[router](https://github.com/Hahyun-Lee/brain-ai-memory/blob/v0.7.0/src/brain_ai_memory/runtime.py)
and [CLI](https://github.com/Hahyun-Lee/brain-ai-memory/blob/v0.7.0/src/brain_ai_memory/cli.py)
are the compatibility references.

## What the evidence allows

A configured server establishes a connection, not successful capture. A
successful write and recall establish those operations, not better answers
than native memory. The [existing reports](../README.md#evidence-status) cover
software contracts, a retrieval pilot and operating experience from a separate
system. They do not establish an end-to-end advantage over native Codex or
Claude memory. Local development qualifications do not change that boundary
or certify the published wheel.
