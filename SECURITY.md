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
