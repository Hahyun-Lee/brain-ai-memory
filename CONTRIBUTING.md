# Contributing

Thanks for considering it. This repo is an installable, local memory-management
layer plus the architecture and evidence behind it. Useful contributions
include improving the adoption workflow, runtime or adapter contracts,
sharpening the mapping, adding a reusable template or worked example, and
reporting where the system breaks for your stack. Hosted-platform features and
organization-specific wiring remain out of scope.

## The one hard rule: clean-room

Everything in this repo is authored generically, for others. **No live content
ever enters the tree:** no real names, no organization or project specifics, no
private data, no credentials, no email addresses. Extract the transferable
concept; never paste in your own system's files. This keeps the repo usable
(generic, not overfit to one setup) and keeps it safe to publish.

Before opening a PR, check your diff for anything that should not be public. If
you are adapting from a real system, the test is simple: a stranger should be
able to read your change without learning anything about a specific person,
team, or dataset.

## Good contributions

- **Sharpen a mapping.** If a brain-to-agent analogy in
  [`docs/01`](docs/01-the-mapping.md) or
  [`schema/brain_components.yaml`](schema/brain_components.yaml) is wrong,
  misleading, or could be clearer, say so. The mapping is an engineering analogy
  that has to earn its keep by making failures diagnosable; argue it on those
  terms.
- **Add a template.** A generic, lang-agnostic skeleton for a construct the docs
  describe. It must run standalone with no dependencies beyond the language's
  standard library (see the existing hook templates).
- **Add a worked example.** A tiny, runnable, no-real-data case that makes a doc
  concrete. Single file, standard library only.
- **Improve the reference runtime.** Preserve the component boundaries, keep
  the local default minimal, add tests, and expose fallback behavior in
  the audit trace rather than hiding it.
- **Report a break.** Where does the architecture not fit your agent stack? A
  clear description of the mismatch is valuable even without a fix.
- **Strengthen the evidence.** The current evidence includes a longitudinal
  single-owner deployment, internal retrieval A/B tests, one deterministic
  capacity simulation, and a public-data retrieval pilot (see
  [`evidence/`](evidence/)). Multi-user replication or a controlled end-to-end
  QA test is especially welcome when it follows the protocol, artifact
  requirements, and claim gates in
  [`benchmarks/`](benchmarks/README.md).

## Benchmark contributions

Do not add a headline score copied from another project or produced under a
different reader model, prompt, budget, or dataset revision. A benchmark PR must
include its run manifest, per-item predictions and retrievals, timing logs, and
the exact scoring procedure. Validate the manifest in release mode before
opening the PR:

```
python3 benchmarks/validate_manifest.py path/to/manifest.json --release
```

Pilot and partial runs are useful for debugging. Label them as pilots, keep them
out of any release-grade headline or scoreboard, and report them only in a
clearly separated pilot section with their limitations.

## Style

- **Run what you add.** Every hook and example must execute standalone. Include a
  self-test or a worked run, and confirm it before opening the PR.
- **Prose discipline.** Keep it plain and direct. At most one em-dash per
  sentence; prefer a colon, period, or parentheses. Claim-first paragraphs.
  State limits honestly rather than overselling.
- **Cross-link.** New docs should link to the components or principles they build
  on, and be linked from a parent (an orphan file is unreachable).

## Preserve the user path

README changes should keep a first-time visitor's decision path intact:

1. Can they state what the repo does and who it is for after the opening screen?
2. Can they run one useful example in about a minute without hidden services or
   credentials?
3. Do they see the expected result before the architecture details?
4. Can they choose one adoption path without accepting the entire system?
5. Are operational exposure, internal A/B evidence, public benchmark results,
   and unmeasured claims visibly separated?

Do not move the brain analogy, implementation taxonomy, or long benchmark
discussion ahead of the runnable success path. Those sections establish depth
after the visitor has established relevance and trust.

## Opening a change

Small, focused PRs with a clear description of the problem and the change. If you
are proposing a new component or channel in the mapping, explain its failure mode
and diagnostic, the same way the existing ones are written. If it is really a
variant of an existing component, extending that one is usually better than
adding a box.
