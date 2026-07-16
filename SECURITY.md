# Security policy

## Reporting a vulnerability

Please do not disclose a suspected vulnerability in a public issue. Use
GitHub's **Security → Report a vulnerability** flow so the report and any
proof-of-concept remain private until a fix or mitigation is available.

Include the affected file or template, the unsafe behavior, the smallest
reproduction you can provide, and whether the issue applies to the generic
public artifact or only to a particular downstream harness.

The runnable hooks in this repository are templates. Adopters are responsible
for testing their event adapter, allow/deny policy, false-positive behavior, and
failure mode before enabling a blocking rule in a live agent.

The reference runtime is an alpha local implementation. Its observer has no
authentication and binds to `127.0.0.1` by default. Do not expose it directly to
a network. Production adopters must add access control, encryption at rest,
backup policy, concurrency controls, and organization-specific secret handling.

The harness executes only an explicit argument vector with `shell=False`, after
the action gate. Treat registering a command or changing a rule as privileged
configuration, and test a blocking policy before relying on it for containment.

## Markdown adoption and host configuration

`brain-ai audit` parses one explicitly selected regular UTF-8 Markdown file,
limited to 2 MiB and 100 kB per line. It
does not render HTML, follow links, expand includes, crawl a home directory, or
collect provider transcripts. Code fences, front matter, HTML comments, and
block quotes are excluded from import candidates. Safe default discovery
rejects symlinked path components and does not cross the selected project root.
Explicit paths are resolved once. On platforms that provide `openat`-style
directory descriptors and `O_NOFOLLOW`, their canonical parent is opened one
component at a time without following a component swapped to a symbolic link;
other platforms retain canonical-path and file-identity checks. The file
identity is checked before and after its bytes are read.
Audit findings are candidates:
an exact text duplicate or two different literal values for the same explicit
key does not establish which statement is true or current.

`brain-ai apply` changes the local typed store, never the source Markdown. It
accepts only decisions saved by `brain-ai review`, requires `--yes`, and refuses
the first operation if the source hash or logical store revision changed after
review. A completed review remains an idempotent receipt lookup and reports if
its source subsequently changed; it never repeats the import.
Rules require an explicit regular expression; exact state requires an explicit
key/value entry. Project-scoped supersession cannot deactivate global memory or
a record linked only to another project. Imported provenance may contain
sensitive paths and text. A newly created runtime uses owner-only directory and
file modes on POSIX systems and writes `.brain-ai/.gitignore`; `brain-ai doctor`
reports a permissive existing store but does not silently change an intentional
shared-store policy. The files are not encrypted. Do not commit or share
`.brain-ai/`.

`brain-ai connect` previews only its managed host-config entry unless `--apply`
is present; unrelated environment values are redacted from preview output.
Project-scoped Codex and Claude Code configuration is intentionally visible in
the project; review it before committing. Invalid or unmanaged config entries
are not rewritten, and an apply stops if the config changed after it was read.
On POSIX platforms with relative directory-descriptor support, the selected
config parent stays pinned across read, compare, atomic replace, and verify.
Other platforms retain resolved-containment, symlink, and content-change
checks but cannot make the same concurrent path-swap guarantee.
`disconnect` removes only the marked configuration for the supplied home and,
when provided, entity. Configuration backups
under `.brain-ai/workflows/config-backups/` are retained until the operator
applies a separate retention policy.

Vault adapters stay within the configured canonical vault root. The local BM25
fallback skips symbolic links, and Smart Connections results whose resolved
paths escape that root are discarded. The configured MCP process is still a
separate executable with its own permissions; review and trust that command
before enabling the adapter.

`rollback` is a logical, evidence-preserving undo. It disables or archives the
records introduced by a batch and restores replaced exact state when safe. It
does not claim secure deletion and refuses to run after unrelated memory changes.
