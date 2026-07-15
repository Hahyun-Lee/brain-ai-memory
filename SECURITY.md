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
