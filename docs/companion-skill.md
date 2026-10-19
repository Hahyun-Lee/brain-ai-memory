# Use the Brain-AI Memory companion skill

The companion teaches an agent when to save a project decision, how to correct
it, and how to retrieve it next session. It contains instructions, not a
runtime or hook installer. The executable MCP server comes from the separately
installed [public package](https://pypi.org/project/brain-ai-memory/0.7.0/).

## Before you start

- Use a project where changing decisions, exact values or session handoffs
  need explicit records. The [README](../README.md#is-it-for-you) helps assess fit.
- Have Python 3.10+ and an MCP-capable agent. The included setup commands use a
  POSIX shell and access to PyPI.
- Choose a project root, one private `.brain-ai` home and a stable entity name.
  Keep that home out of source control. Its SQLite/JSON files are not encrypted.
- Reuse a configured connection. Do not downgrade an existing runtime or
  replace its hooks just to follow a fresh-install example.

## Connect the runtime, then add the instructions

For a new installation, follow the
[tools-mode setup](../README.md#connect-codex-or-claude-code). The runtime
previews the actual host configuration before `--apply`, pins the interpreter
and local home, and locks the connection to the selected project. Complete
host approval and reconnect or start a new session after applying it.

For a direct repository copy under MIT, install the
[`skills/brain-ai-memory/`](../skills/brain-ai-memory/) folder in the skill
directory supported by your agent. `SKILL.md` is self-contained, including the
fresh-install commands and released tool routine. Optional `agents/openai.yaml`
provides UI metadata; it does not register the MCP server. For project-local
use, copy the folder so that its entrypoint has the following path:

| Host | Path inside your project | Official instructions |
|---|---|---|
| Codex | `.agents/skills/brain-ai-memory/SKILL.md` | [Build skills](https://developers.openai.com/codex/skills#where-codex-loads-local-skills) |
| Claude Code | `.claude/skills/brain-ai-memory/SKILL.md` | [Choose where skills load](https://code.claude.com/docs/en/skills#choose-where-skills-load) |

These are the official local discovery paths checked on 2026-10-19. Start a
fresh project session after installation if the skill is not yet visible.

Installing through Agensi uses its agent-delivery path instead of a local
repository copy. The open-source runtime is still installed separately; see
[distribution](#distribution) below.

## Confirm the connection

During ordinary work, use this routine on a confirmed fact the user intends to
retain. A connection-status message alone is insufficient.

1. Resolve the configured project scope. On a locked connection, omit `entity`
   in tool calls.
2. Resume the project with `brain_resume`; an initial `not_found` handoff is
   normal. Query relevant context with `brain_context`.
3. Save the confirmed fact with `brain_remember(kind="semantic", text=...)`.
   Use `kind="state", key=..., value_json=...` for an exact value; the value
   must be JSON text, such as `value_json='"stable"'`.
4. Inspect the write result and retrieve that record. On v0.7.0, use
   `brain_context(query="metric KEY")` for a known state key and inspect the
   matching `memory.IPS` entry. Do not count an echoed query as recall.
5. Correct an exact value under the same key, or use
   `brain_supersede(old_id=..., new_text=...)` for a replaced semantic fact.
   Save the source of the correction.
6. At handoff, use `brain_checkpoint(summary=..., next_actions=[...])` for
   completed work and agreed next actions. This does not replace fact writes.

These are user checks for an actual task, not a benchmark result. If a write
or retrieval fails, report the failed step; do not claim durable memory from
connection availability. The [full skill](../skills/brain-ai-memory/SKILL.md)
contains the scoped CLI fallback and uncertainty handling.

## Choose automation separately

This companion starts with **tools mode**: the agent follows a routine and
calls the tools. Skill instructions do not enforce compliance or automatically
capture a conversation. The [optional session loop](08-autonomous-loop.md)
supplies supported recall and checkpoint events through host hooks.
Source-freshness holds belong to that loop's review workflow; a tools-only
action check does not itself perform source-freshness enforcement.

The initial profile targets published **v0.7.0**. It does not require
`brain_scope` or newer development recall corrections. See the
[release boundary](release-and-operating-boundary.md) and
[memory self-monitoring](memory-self-monitoring.md).

## Remove or change the connection

Use the runtime's preview/apply removal procedure in the
[MCP guide](07-mcp-server.md#install-and-start). Removing the host connection
does not erase the local store. Review the stored records and your backup or
retention needs separately. For a local repository skill copy, remove that
copy through the host's skill-management path.

## Distribution

The repository and companion are MIT licensed. No marketplace purchase is
required for direct repository use. An Agensi-delivered copy is accessed
through the connected agent; its [delivery terms, section 5.2](https://www.agensi.io/terms)
prohibit saving or exporting delivered skill files. That delivery restriction
does not make the separately installed open-source runtime a paid dependency.

For creators, the proposed upload ZIP places `SKILL.md` at its root, with
optional `agents/openai.yaml` and the repository `LICENSE`. It contains no
runtime, credentials, memory database, installer or hook script. The
[creator checklist](https://www.agensi.io/learn/skill-md-creator-checklist) and
[supporting-file guide](https://www.agensi.io/learn/how-to-write-skill-md-supporting-files)
describe packaging; bundled helper-script local execution is not established
here. This companion uses the public external runtime and avoids that dependency.

Frontmatter, released interfaces, links and archive contents can be checked
statically. Those checks do not establish agent compliance, universal host
support, market demand or improved answer quality.
