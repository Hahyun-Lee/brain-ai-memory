"""brain-ai command-line interface."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shlex
import sys
from pathlib import Path

from . import __version__
from .config import resolve_home
from .control import serve
from .integrations import loop_connection_change, loop_connection_status
from .privacy import permission_issues
from .runtime import BrainAIRuntime
from .storage import LIFECYCLE_OPERATIONS
from .workspace import (
    WorkflowConflict,
    apply_review,
    build_audit,
    build_review,
    connection_change,
    connection_status,
    load_artifact,
    resolve_review,
    rollback_batch,
    safe_display,
    save_audit,
    save_review,
)

CONNECTION_INSTALL_HINT = (
    "install agent connection support from the repository checkout with "
    "python -m pip install '.[mcp]'"
)


def emit(value, as_json: bool = False) -> None:
    if as_json or isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brain-ai",
        description="Manage typed, scoped memory across long-running agent sessions",
    )
    parser.add_argument("--home", help="runtime directory (default: $BRAIN_AI_HOME or ./.brain-ai)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    init = sub.add_parser("init", help="initialize a local runtime")
    init.add_argument("--json", action="store_true")

    audit = sub.add_parser("audit", help="inspect an existing Markdown memory file without changing it")
    audit.add_argument("path", nargs="?", help="MEMORY.md (auto-detects ./.claude/MEMORY.md or ./MEMORY.md)")
    audit.add_argument("--entity", required=True, help="stable project name for imported records")
    audit.add_argument("--root", default=".", help="project root used only for safe default discovery")
    audit.add_argument("--no-save", action="store_true", help="pure preview; do not save an audit plan")
    audit.add_argument("--json", action="store_true")

    review = sub.add_parser("review", help="inspect an audit and record explicit import decisions")
    review.add_argument("audit_id")
    review.add_argument("--approve-ready", action="store_true", help="approve unambiguous semantic/episodic entries and skip exact duplicates")
    review.add_argument("--set", action="append", default=[], metavar="ITEM=ACTION", help="ACTION is semantic, episodic, state, or skip")
    review.add_argument("--rule", action="append", default=[], metavar="ITEM=SAFE_PATTERN", help="explicitly enable an imported procedural rule using the bounded safe pattern subset")
    review.add_argument("--rule-effect", choices=("warn", "block"), default="warn")
    review.add_argument("--supersede", action="append", default=[], metavar="ITEM=MEMORY_ID", help="replace one active semantic record while retaining its history")
    review.add_argument("--json", action="store_true")

    apply_plan = sub.add_parser("apply", help="import only the decisions saved in a review")
    apply_plan.add_argument("review_or_audit_id")
    apply_plan.add_argument("--yes", action="store_true", help="confirm mutation of the local typed memory store")
    apply_plan.add_argument("--json", action="store_true")

    rollback = sub.add_parser("rollback", help="logically undo one import batch while retaining evidence")
    rollback.add_argument("batch_or_review_id")
    rollback.add_argument("--yes", action="store_true")
    rollback.add_argument("--json", action="store_true")

    connect = sub.add_parser("connect", help="preview or connect Brain-AI Memory to an agent")
    connect.add_argument("host", choices=("codex", "claude-code"))
    connect.add_argument("--entity", required=True)
    connect.add_argument("--scope", choices=("project", "user"), default="project")
    connect.add_argument(
        "--mode",
        choices=("tools", "loop"),
        default="tools",
        help="tools: on-demand memory tools; loop: opt-in automatic recall and checkpoints",
    )
    connect.add_argument("--project-root", default=".")
    connect.add_argument("--apply", action="store_true", help="write the shown host-config change")
    connect.add_argument("--json", action="store_true")

    disconnect = sub.add_parser("disconnect", help="preview or remove a managed agent connection")
    disconnect.add_argument("host", choices=("codex", "claude-code"))
    disconnect.add_argument("--entity", default="", help="optional label retained in preview commands")
    disconnect.add_argument("--scope", choices=("project", "user"), default="project")
    disconnect.add_argument(
        "--mode",
        choices=("tools", "loop"),
        default="tools",
        help="remove the on-demand tools connection or the full autonomous loop",
    )
    disconnect.add_argument("--project-root", default=".")
    disconnect.add_argument("--apply", action="store_true")
    disconnect.add_argument("--json", action="store_true")

    remember = sub.add_parser("remember", help="write to a differentiated memory store")
    remember.add_argument("--type", choices=("episodic", "semantic", "rule", "state"), required=True)
    remember.add_argument("--text")
    remember.add_argument("--source", default="cli")
    remember.add_argument("--tags", nargs="*", default=[])
    remember.add_argument("--entity", action="append", default=[], help="entity id, name, or alias; repeatable")
    remember.add_argument("--promote", choices=("semantic", "rule"))
    remember.add_argument("--pattern", help="bounded safe-pattern subset for a procedural rule")
    remember.add_argument("--effect", choices=("block", "warn"), default="block")
    remember.add_argument("--key")
    remember.add_argument("--value")
    remember.add_argument("--json", action="store_true")

    recall = sub.add_parser("recall", help="route and retrieve component-specific memory")
    recall.add_argument("query")
    recall.add_argument("--action")
    recall.add_argument("--entity", help="scope recall to an entity id, name, or alias")
    recall.add_argument("--limit", type=int)
    recall.add_argument("--json", action="store_true")

    run = sub.add_parser("run", help="prepare an auditable context bundle for any executor")
    run.add_argument("query")
    run.add_argument("--action")
    run.add_argument("--entity", help="scope context and rules to one entity")
    run.add_argument("--limit", type=int)
    run.add_argument("--json", action="store_true")

    harness = sub.add_parser("harness", help="guard and run an explicit command without a shell")
    harness.add_argument("--query", required=True)
    harness.add_argument("--timeout", type=float, default=60)
    harness.add_argument("--cwd")
    harness.add_argument("--entity", help="scope recalled memory and rules to one entity")
    harness.add_argument("--json", action="store_true")
    harness.add_argument("command", nargs=argparse.REMAINDER)

    sequence = sub.add_parser("sequence", help="run explicit fallback steps until one succeeds")
    sequence.add_argument("--query", required=True)
    sequence.add_argument(
        "--step", action="append", required=True,
        help='JSON argv array; repeat for fallbacks, e.g. --step \"[\\\"python3\\\",\\\"check.py\\\"]\"',
    )
    sequence.add_argument("--timeout", type=float, default=60)
    sequence.add_argument("--cwd")
    sequence.add_argument("--entity", help="scope recalled memory and rules to one entity")
    sequence.add_argument("--json", action="store_true")

    checkpoint = sub.add_parser("checkpoint", help="record state and consolidation candidates")
    checkpoint.add_argument("--summary", default="")
    checkpoint.add_argument("--json", action="store_true")

    handoff = sub.add_parser("handoff", help="write a project-scoped checkpoint for the next session")
    handoff.add_argument("--entity", required=True)
    handoff.add_argument("--summary", default="")
    handoff.add_argument("--next", action="append", default=[], dest="next_actions")
    handoff.add_argument("--json", action="store_true")

    resume = sub.add_parser("resume", help="read the latest handoff for exactly one project scope")
    resume.add_argument("--entity", required=True)
    resume.add_argument("--json", action="store_true")

    consolidate = sub.add_parser("consolidate", help="preview or apply episodic promotion")
    consolidate.add_argument("--apply", action="store_true", help="apply approved candidates; default is preview")
    consolidate.add_argument("--json", action="store_true")

    supersede = sub.add_parser("supersede", help="reconsolidate stale semantic memory")
    supersede.add_argument("old_id")
    supersede.add_argument("--text", required=True)
    supersede.add_argument("--source", default="cli")
    supersede.add_argument("--tags", nargs="*", default=[])
    supersede.add_argument(
        "--entity",
        help="replace only this entity's binding; omit only for an intentional global update",
    )
    supersede.add_argument("--json", action="store_true")

    lifecycle = sub.add_parser("lifecycle", help="record one of seven lifecycle decisions")
    lifecycle.add_argument("target_type", choices=("episodic", "semantic"))
    lifecycle.add_argument("target_id")
    lifecycle.add_argument("operation", choices=sorted(LIFECYCLE_OPERATIONS))
    lifecycle.add_argument("--reason", default="")
    lifecycle.add_argument("--json", action="store_true")

    rule = sub.add_parser("rule", help="inspect or change stored procedural rules")
    rule_sub = rule.add_subparsers(dest="rule_command", required=True)
    rule_list = rule_sub.add_parser(
        "list", help="show active, disabled, and automatically quarantined rules"
    )
    rule_list.add_argument("--json", action="store_true")
    rule_disable = rule_sub.add_parser(
        "disable", help="disable one rule without deleting its history"
    )
    rule_disable.add_argument("rule_id")
    rule_disable.add_argument("--reason", default="operator request")
    rule_disable.add_argument("--yes", action="store_true")
    rule_disable.add_argument("--json", action="store_true")
    rule_enable = rule_sub.add_parser(
        "enable", help="re-enable one rule only if it passes current safety checks"
    )
    rule_enable.add_argument("rule_id")
    rule_enable.add_argument("--yes", action="store_true")
    rule_enable.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="show component counts and runtime health")
    status.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor", help="check local configuration and adapter readiness")
    doctor.add_argument("--host", choices=("codex", "claude-code"))
    doctor.add_argument("--scope", choices=("project", "user"), default="project")
    doctor.add_argument(
        "--mode",
        choices=("tools", "loop"),
        default="tools",
        help="check on-demand tools or the opt-in autonomous loop",
    )
    doctor.add_argument("--project-root", default=".")
    doctor.add_argument("--entity", help="also require this configured default entity")
    doctor.add_argument("--json", action="store_true")

    dashboard = sub.add_parser("serve", help="start the read-only local Command Center")
    dashboard.add_argument("--host")
    dashboard.add_argument("--port", type=int)

    demo = sub.add_parser("demo", help="run a local memory-kernel demonstration")
    demo.add_argument("--json", action="store_true")

    tour = sub.add_parser(
        "tour",
        help="show entity binding, recall, state, guard, fallback, and lifecycle outcomes",
    )
    tour.add_argument("--json", action="store_true")

    entity = sub.add_parser("entity", help="create and inspect stable entity identities")
    entity_sub = entity.add_subparsers(dest="entity_command", required=True)
    entity_add = entity_sub.add_parser("add", help="create or resolve an entity")
    entity_add.add_argument("--name", required=True)
    entity_add.add_argument("--type", default="concept")
    entity_add.add_argument("--alias", action="append", default=[])
    entity_add.add_argument("--json", action="store_true")
    entity_list = entity_sub.add_parser("list", help="list entities")
    entity_list.add_argument("--query")
    entity_list.add_argument("--json", action="store_true")
    entity_show = entity_sub.add_parser("show", help="show an entity and its relations")
    entity_show.add_argument("reference")
    entity_show.add_argument("--json", action="store_true")

    relation = sub.add_parser("relation", help="create and inspect typed entity relations")
    relation_sub = relation.add_subparsers(dest="relation_command", required=True)
    relation_add = relation_sub.add_parser("add", help="link two existing entities")
    relation_add.add_argument("subject")
    relation_add.add_argument("predicate")
    relation_add.add_argument("object_ref")
    relation_add.add_argument("--source", default="cli")
    relation_add.add_argument("--json", action="store_true")
    relation_list = relation_sub.add_parser("list", help="list relations")
    relation_list.add_argument("--entity")
    relation_list.add_argument("--json", action="store_true")

    ontology = sub.add_parser("ontology", help="validate and inspect the executable component schema")
    ontology.add_argument("--full", action="store_true")
    ontology.add_argument("--json", action="store_true")

    mcp = sub.add_parser("mcp", help="serve Brain-AI tools and resources over MCP")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_serve = mcp_sub.add_parser("serve", help="start the MCP server")
    mcp_serve.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    mcp_serve.add_argument("--host", default="127.0.0.1")
    mcp_serve.add_argument("--port", type=int, default=8000)
    mcp_serve.add_argument("--entity", default="", help="default entity scope")
    mcp_serve.add_argument(
        "--locked-entity",
        default="",
        help="entity scope that calls served by this process cannot override",
    )
    return parser


def parse_value(value: str | None):
    if value is None:
        raise ValueError("--value is required for state memory")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def doctor(
    runtime: BrainAIRuntime,
    host: str | None = None,
    *,
    scope: str = "project",
    project_root: str | Path = ".",
    entity: str | None = None,
    mode: str = "tools",
) -> dict:
    semantic = runtime.config.get("semantic", {})
    vault = semantic.get("vault_path")
    command = semantic.get("mcp_command") or []
    private_paths = [
        runtime.store.db_path,
        runtime.store.events_path,
        runtime.store.audit_path,
        runtime.store.checkpoints_path,
        runtime.home / "config.json",
        runtime.home / ".gitignore",
    ]
    privacy_warnings = permission_issues(runtime.home, private_paths)
    ignore_path = runtime.home / ".gitignore"
    try:
        runtime_home_git_ignored = any(
            line.strip() == "*"
            for line in ignore_path.read_text(encoding="utf-8").splitlines()
        )
    except (OSError, UnicodeError):
        runtime_home_git_ignored = False
    checks = {
        "home_exists": runtime.home.is_dir(),
        "database_exists": runtime.store.db_path.is_file(),
        "semantic_backend": semantic.get("backend", "local"),
        "vault_exists": None if not vault else Path(vault).expanduser().is_dir(),
        "mcp_command_configured": bool(command),
        "mcp_support_installed": importlib.util.find_spec("mcp") is not None,
        "runtime_home_git_ignored": runtime_home_git_ignored,
        "private_permissions": not privacy_warnings,
        "permission_warnings": privacy_warnings,
        "ontology_valid": runtime.ontology_summary["component_count"] > 0,
    }
    quarantined_rules = runtime.store.applicable_rule_quarantines(entity)
    checks["quarantined_rule_count"] = len(quarantined_rules)
    checks["quarantined_rule_ids"] = [rule["id"] for rule in quarantined_rules]
    checks["ready"] = (
        checks["home_exists"]
        and checks["database_exists"]
        and checks["private_permissions"]
        and checks["runtime_home_git_ignored"]
        and checks["ontology_valid"]
        and not quarantined_rules
    )
    if host:
        if mode == "loop":
            checks["connection"] = loop_connection_status(
                runtime.home,
                host,
                scope=scope,
                project_root=project_root,
                entity=entity,
            )
            checks["configured"] = checks["connection"]["configured"]
            checks["active"] = checks["connection"]["active"]
            checks["ready"] = (
                checks["ready"]
                and checks["mcp_support_installed"]
                and checks["connection"]["active"]
            )
            if checks["configured"] and not checks["active"]:
                loop_error = checks["connection"]["lifecycle"].get("loop_error")
                if loop_error:
                    checks["next_action"] = (
                        "inspect the automatic-session error, then retry the failed "
                        f"host event: {loop_error}"
                    )
                else:
                    checks["next_action"] = (
                        "review the project hooks with /hooks, then start a new Codex session"
                        if host == "codex"
                        else "approve the project hooks, then start a new Claude Code session"
                    )
            elif not checks["configured"]:
                checks["next_action"] = (
                    f"preview: brain-ai connect {host} --entity <project> "
                    "--mode loop"
                )
        else:
            checks["connection"] = connection_status(
                runtime.home,
                host,
                scope=scope,
                project_root=project_root,
                entity=entity,
            )
            checks["ready"] = (
                checks["ready"]
                and checks["mcp_support_installed"]
                and checks["connection"]["configured"]
            )
            checks["migration_required"] = checks["connection"].get(
                "migration_required", False
            )
            if checks["migration_required"]:
                checks["next_action"] = (
                    "upgrade the managed project connection to locked entity scope: "
                    + checks["connection"]["migration_command"]
                )
        if not checks["mcp_support_installed"]:
            checks["next_action"] = CONNECTION_INSTALL_HINT
    if quarantined_rules:
        checks["ready"] = False
        checks["next_action"] = (
            f"review {len(quarantined_rules)} quarantined legacy rule(s) with "
            f"brain-ai --home {shlex.quote(str(runtime.home))} rule list --json; "
            "create safe replacements with brain-ai remember --type rule, then "
            "acknowledge each old rule with brain-ai rule disable RULE_ID --yes"
        )
    return checks


def run_demo(runtime: BrainAIRuntime) -> dict:
    knowledge = runtime.store.put_knowledge(
        "Atlas releases require a completed review before deployment.", source="demo", tags=["release"]
    )
    runtime.store.set_state("atlas_open_reviews", 3, source="demo")
    existing = [rule for rule in runtime.store.rules() if rule["source"] == "demo"]
    rule = existing[0] if existing else runtime.store.add_rule(
        r"deploy atlas", effect="warn", reason="confirm that the release review is complete", source="demo"
    )
    episode = runtime.store.append_event(
        "The Atlas release window moved from Friday to Thursday.",
        source="demo", tags=["release", "update"], promote_to="semantic",
    )
    prepared = runtime.process(
        "Atlas의 최근 배포 규칙과 open review 개수는?",
        proposed_action="deploy atlas",
    )
    checkpoint = runtime.checkpoint("demo completed")
    return {
        "knowledge_id": knowledge["id"], "rule_id": rule["id"], "episode_id": episode["id"],
        "process": prepared, "checkpoint": checkpoint,
        "next": "brain-ai consolidate (preview), then brain-ai consolidate --apply",
    }


def run_tour(runtime: BrainAIRuntime) -> dict:
    project = runtime.store.put_entity("Atlas", entity_type="project")
    release = runtime.store.put_entity("Atlas 2.1", entity_type="release", aliases=["2.1"])
    runtime.store.add_relation(release["id"], "belongs_to", project["id"], source="tour")

    old = runtime.store.put_knowledge(
        "Atlas 2.1 release day is Friday.", source="tour", entities=[release["id"]]
    )
    updated = runtime.reconsolidate(
        old["id"], "Atlas 2.1 release day is Thursday.", source="tour"
    )
    runtime.store.append_event(
        "Atlas 2.1 moved from Friday to Thursday after the release review.",
        source="tour",
        entities=[release["id"]],
    )
    runtime.store.set_state("open_reviews", 3, source="tour", entity=release["id"])
    existing_rules = [rule for rule in runtime.store.rules() if rule["source"] == "tour"]
    if not existing_rules:
        runtime.store.add_rule(
            r"deploy production",
            effect="block",
            reason="release approval is required before production deployment",
            source="tour",
            entities=[release["id"]],
        )

    prepared = runtime.process(
        "What is the Atlas 2.1 release day, and how many open reviews remain?",
        proposed_action="deploy production",
        entity=release["id"],
    )
    fallback = runtime.execute_sequence(
        "validate the release with a host-supplied fallback",
        [
            [sys.executable, "-c", "raise SystemExit(1)"],
            [sys.executable, "-c", "print('fallback validation passed')"],
        ],
        entity=release["id"],
    )
    checkpoint = runtime.handoff(
        release["id"],
        summary="local tour completed",
        next_actions=["Continue the Atlas 2.1 release workflow"],
    )
    resumed = runtime.resume(release["id"])
    state = next(
        item for item in prepared["memory"].get("IPS", []) if item["key"] == "open_reviews"
    )
    active_fact = next(
        item
        for item in prepared["memory"].get("ATL", [])
        if item["id"] == updated["new_id"]
    )
    return {
        "entity": f"{release['name']} → belongs_to → {project['name']}",
        "found": active_fact["text"],
        "exact_state": f"open_reviews = {state['value']}",
        "blocked": prepared["gate"]["reason"],
        "fallback": f"completed after {fallback['attempt_count']} attempts",
        "updated": "Friday → superseded by → Thursday",
        "checkpoint": checkpoint["id"],
        "evidence": {
            "context": prepared,
            "fallback_sequence": fallback,
            "handoff": checkpoint,
            "resumed_handoff": resumed,
        },
    }


def emit_tour(value: dict, as_json: bool) -> None:
    if as_json:
        emit(value, True)
        return
    print("Brain-AI Memory: current memory and a session handoff")
    print(f"1  BIND     {value['entity']}")
    print(f"2  RECALL   {value['found']}")
    print(f"3  STATE    {value['exact_state']}")
    print(f"4  UPDATE   {value['updated']}")
    print(f"5  HANDOFF  checkpoint {value['checkpoint']}")
    print("Optional action checks")
    print(f"6  GUARD    blocked: {value['blocked']}")
    print(f"7  FALLBACK {value['fallback']}")


def _command_prefix(home: Path) -> str:
    return f"brain-ai --home {shlex.quote(str(home))}"


def emit_audit(
    value: dict,
    plan_path: Path | None,
    as_json: bool,
    home: Path,
) -> None:
    if as_json:
        emit({**value, "plan_path": str(plan_path) if plan_path else None}, True)
        return
    counts = value["counts"]
    print(f"Audited {value['source']['path']}")
    print(f"Entity: {value['entity']['name']}")
    print(f"Entries: {counts['entries']}")
    print()
    print(f"Ready to import:       {counts['ready']}")
    print(f"Needs review:          {counts['needs_review']}")
    print(f"Duplicate candidates:  {counts['duplicate_candidates']}")
    print(f"Possible conflicts:    {counts['possible_conflicts']}")
    print()
    if plan_path:
        print(f"Review plan: {plan_path}")
        print("Source file and memory store unchanged.")
        print(f"Next: {_command_prefix(home)} review {value['id']}")
    else:
        print("Pure preview: no files or memory records changed.")


def emit_review(
    audit: dict,
    review: dict | None,
    plan_path: Path | None,
    as_json: bool,
    home: Path,
) -> None:
    if as_json:
        emit(
            {
                "audit": audit,
                "review": review,
                "review_path": str(plan_path) if plan_path else None,
            },
            True,
        )
        return
    if review:
        counts = review["counts"]
        print(f"Review saved: {review['id']}")
        print(f"Approved: {counts['approved']}  Skipped: {counts['skipped']}  Unresolved: {counts['unresolved']}")
        print("Source file and memory records unchanged.")
        print(f"Next: {_command_prefix(home)} apply {review['id']} --yes")
        return
    print(f"Audit {audit['id']} · {audit['entity']['name']}")
    findings_by_item: dict[str, list[str]] = {}
    for finding in audit["findings"]:
        for item_id in finding.get("candidate_ids", []):
            findings_by_item.setdefault(item_id, []).append(finding["kind"])
        if finding.get("duplicate"):
            findings_by_item.setdefault(finding["duplicate"], []).append(finding["kind"])
    for item in audit["entries"]:
        labels = ",".join(findings_by_item.get(item["id"], []))
        suffix = f" · {labels}" if labels else ""
        print(
            f"{item['id']}  L{item['line_start']}-{item['line_end']}  "
            f"{item['suggested_type']}/{item['status']}{suffix}"
        )
        print(f"  {safe_display(item['text'])}")
    print()
    print("No decisions saved. Use --approve-ready or explicit --set/--rule/--supersede choices.")


def emit_apply(value: dict, as_json: bool, home: Path) -> None:
    if as_json:
        emit(value, True)
        return
    imported = sum(item["status"] == "imported" for item in value.get("results", []))
    existing = sum(item["status"].startswith("already_") for item in value.get("results", []))
    print(f"Import batch {value['id']}: {value['status']}")
    print(f"Imported: {imported}  Already present: {existing}")
    print("Source MEMORY.md unchanged; provenance is stored with every imported record.")
    if value.get("entity"):
        name = value["entity"]["name"]
        print(
            f"Next: {_command_prefix(home)} connect codex "
            f"--entity {shlex.quote(name)}"
        )


def emit_connection(value: dict, as_json: bool) -> None:
    if as_json:
        emit(value, True)
        return
    path = value.get("path") or value.get("lifecycle", {}).get("hook_config")
    label = f"{value.get('mode', 'tools')} mode"
    print(f"{value['host']} {label} {value['status']}: {path}")
    if value["diff"]:
        print(value["diff"], end="" if value["diff"].endswith("\n") else "\n")
    elif not value["changed"]:
        print("No configuration change needed.")
    if value.get("next"):
        print(f"Next: {value['next']}")


def emit_doctor(value: dict, as_json: bool) -> None:
    if as_json:
        emit(value, True)
        return
    print(f"Brain-AI Memory: {'ready' if value['ready'] else 'attention needed'}")
    print(
        "Local store: "
        + ("ready" if value["home_exists"] and value["database_exists"] else "not ready")
    )
    if "connection" in value:
        connection = value["connection"]
        if connection.get("mode") == "loop":
            print(
                "Automatic session memory: "
                f"configured={'yes' if value.get('configured') else 'no'}, "
                f"active={'yes' if value.get('active') else 'no'}"
            )
            errors = [
                connection.get("mcp", {}).get("error"),
                connection.get("lifecycle", {}).get("error"),
            ]
        else:
            print(
                "Agent connection: "
                + ("configured" if connection.get("configured") else "not configured")
            )
            errors = [connection.get("error")]
        for error in errors:
            if error:
                print(f"Problem: {error}")
        print(
            "Agent connection support: "
            + ("installed" if value["mcp_support_installed"] else "missing")
        )
    for warning in value.get("permission_warnings", []):
        print(f"Permission warning: {warning}")
    if value.get("quarantined_rule_count"):
        print(f"Quarantined legacy rules: {value['quarantined_rule_count']}")
    if value.get("next_action"):
        print(f"Next: {value['next_action']}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = resolve_home(args.home)
    try:
        # These commands deliberately run before BrainAIRuntime construction.
        # An audit preview must not create SQLite/config files as a side effect.
        if args.subcommand == "audit":
            value = build_audit(args.path, entity=args.entity, root=args.root)
            plan_path = None if args.no_save else save_audit(home, value)
            emit_audit(value, plan_path, args.json, home)
            return 0
        if args.subcommand == "review":
            audit = load_artifact(home, "audits", args.audit_id)
            mutating_review = bool(
                args.approve_ready or args.set or args.rule or args.supersede
            )
            if not mutating_review:
                emit_review(audit, None, None, args.json, home)
                return 0
            runtime = BrainAIRuntime(home)
            value = build_review(
                audit,
                runtime.store,
                approve_ready=args.approve_ready,
                assignments=args.set,
                rules=args.rule,
                supersedes=args.supersede,
                rule_effect=args.rule_effect,
            )
            plan_path = save_review(home, value)
            emit_review(audit, value, plan_path, args.json, home)
            return 0
        if args.subcommand == "apply":
            if not args.yes:
                raise ValueError("apply changes the typed memory store; rerun with --yes")
            review = resolve_review(home, args.review_or_audit_id)
            audit = load_artifact(home, "audits", review["audit_id"])
            runtime = BrainAIRuntime(home)
            emit_apply(
                apply_review(home, runtime.store, review, audit),
                args.json,
                home,
            )
            return 0
        if args.subcommand == "rollback":
            if not args.yes:
                raise ValueError("rollback changes active memory; rerun with --yes")
            runtime = BrainAIRuntime(home)
            emit(rollback_batch(home, runtime.store, args.batch_or_review_id), args.json)
            return 0
        if args.subcommand in {"connect", "disconnect"}:
            if (
                args.subcommand == "connect"
                and args.apply
                and importlib.util.find_spec("mcp") is None
            ):
                raise ValueError(CONNECTION_INSTALL_HINT)
            if args.subcommand == "connect" and args.apply:
                runtime = BrainAIRuntime(home)
                try:
                    runtime.store.get_entity(args.entity)
                except KeyError as exc:
                    raise ValueError(
                        "entity does not exist in the typed store; apply an audit or run brain-ai entity add first"
                    ) from exc
            if args.mode == "loop":
                value = loop_connection_change(
                    home,
                    args.host,
                    entity=args.entity,
                    scope=args.scope,
                    project_root=args.project_root,
                    disconnect=args.subcommand == "disconnect",
                    apply=args.apply,
                )
            else:
                value = connection_change(
                    home,
                    args.host,
                    entity=args.entity,
                    scope=args.scope,
                    project_root=args.project_root,
                    disconnect=args.subcommand == "disconnect",
                    apply=args.apply,
                )
            emit_connection(value, args.json)
            return 0

        runtime = BrainAIRuntime(home)
        if args.subcommand == "init":
            emit({"status": "initialized", **runtime.status()}, args.json)
        elif args.subcommand == "remember":
            if args.type == "episodic":
                if not args.text:
                    raise ValueError("--text is required for episodic memory")
                value = runtime.store.append_event(
                    args.text, source=args.source, tags=args.tags,
                    promote_to=args.promote, rule_pattern=args.pattern, entities=args.entity,
                )
            elif args.type == "semantic":
                if not args.text:
                    raise ValueError("--text is required for semantic memory")
                value = runtime.store.put_knowledge(
                    args.text, source=args.source, tags=args.tags, entities=args.entity
                )
            elif args.type == "rule":
                if not args.pattern or not args.text:
                    raise ValueError("--pattern and --text (reason) are required for rule memory")
                value = runtime.store.add_rule(
                    args.pattern,
                    effect=args.effect,
                    reason=args.text,
                    source=args.source,
                    entities=args.entity,
                )
            else:
                if not args.key:
                    raise ValueError("--key is required for state memory")
                if len(args.entity) > 1:
                    raise ValueError("exact state accepts at most one --entity")
                value = runtime.store.set_state(
                    args.key,
                    parse_value(args.value),
                    source=args.source,
                    entity=(args.entity or [None])[0],
                )
            emit(value, args.json)
        elif args.subcommand == "rule":
            if args.rule_command == "list":
                emit(runtime.store.admin_rules(), args.json)
            elif args.rule_command == "disable":
                if not args.yes:
                    raise ValueError(
                        "rule disable changes enforcement; rerun with --yes"
                    )
                emit(
                    runtime.store.disable_rule(args.rule_id, reason=args.reason),
                    args.json,
                )
            else:
                if not args.yes:
                    raise ValueError(
                        "rule enable changes enforcement; rerun with --yes"
                    )
                emit(runtime.store.enable_rule(args.rule_id), args.json)
        elif args.subcommand == "recall":
            emit(
                runtime.recall(
                    args.query,
                    limit=args.limit,
                    proposed_action=args.action,
                    entity=args.entity,
                ),
                args.json,
            )
        elif args.subcommand == "run":
            emit(
                runtime.process(
                    args.query,
                    proposed_action=args.action,
                    limit=args.limit,
                    entity=args.entity,
                ),
                args.json,
            )
        elif args.subcommand == "harness":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            emit(
                runtime.execute(
                    args.query,
                    command,
                    timeout=args.timeout,
                    cwd=args.cwd,
                    entity=args.entity,
                ),
                args.json,
            )
        elif args.subcommand == "sequence":
            steps = []
            for raw in args.step:
                step = json.loads(raw)
                if not isinstance(step, list) or not step or not all(isinstance(item, str) for item in step):
                    raise ValueError("each --step must be a non-empty JSON array of strings")
                steps.append(step)
            emit(
                runtime.execute_sequence(
                    args.query,
                    steps,
                    timeout=args.timeout,
                    cwd=args.cwd,
                    entity=args.entity,
                ),
                args.json,
            )
        elif args.subcommand == "checkpoint":
            emit(runtime.checkpoint(args.summary), args.json)
        elif args.subcommand == "handoff":
            emit(
                runtime.handoff(
                    args.entity,
                    summary=args.summary,
                    next_actions=args.next_actions,
                ),
                args.json,
            )
        elif args.subcommand == "resume":
            emit(runtime.resume(args.entity), args.json)
        elif args.subcommand == "consolidate":
            emit(runtime.consolidate(apply=args.apply), args.json)
        elif args.subcommand == "supersede":
            emit(
                runtime.reconsolidate(
                    args.old_id,
                    args.text,
                    source=args.source,
                    tags=args.tags,
                    entity=args.entity,
                ),
                args.json,
            )
        elif args.subcommand == "lifecycle":
            emit(runtime.store.record_lifecycle(args.target_type, args.target_id, args.operation, args.reason), args.json)
        elif args.subcommand == "status":
            emit(runtime.status(), args.json)
        elif args.subcommand == "doctor":
            emit_doctor(
                doctor(
                    runtime,
                    args.host,
                    scope=args.scope,
                    project_root=args.project_root,
                    entity=args.entity,
                    mode=args.mode,
                ),
                args.json,
            )
        elif args.subcommand == "serve":
            observer = runtime.config.get("observer", {})
            serve(runtime, args.host or observer.get("host", "127.0.0.1"), args.port or int(observer.get("port", 8765)))
        elif args.subcommand == "demo":
            emit(run_demo(runtime), args.json)
        elif args.subcommand == "tour":
            emit_tour(run_tour(runtime), args.json)
        elif args.subcommand == "entity":
            if args.entity_command == "add":
                value = runtime.store.put_entity(
                    args.name, entity_type=args.type, aliases=args.alias
                )
            elif args.entity_command == "list":
                value = runtime.store.entities(args.query)
            else:
                value = runtime.store.get_entity(args.reference)
                value["relations"] = runtime.store.relations(value["id"])
            emit(value, args.json)
        elif args.subcommand == "relation":
            if args.relation_command == "add":
                value = runtime.store.add_relation(
                    args.subject,
                    args.predicate,
                    args.object_ref,
                    source=args.source,
                )
            else:
                value = runtime.store.relations(args.entity)
            emit(value, args.json)
        elif args.subcommand == "ontology":
            emit(runtime.ontology if args.full else runtime.ontology_summary, args.json)
        elif args.subcommand == "mcp":
            from .mcp_server import create_mcp_server

            server = create_mcp_server(
                runtime.home,
                host=args.host,
                port=args.port,
                default_entity=args.entity,
                locked_entity=args.locked_entity,
            )
            server.run(transport=args.transport)
        return 0
    except WorkflowConflict as exc:
        print(f"brain-ai: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"brain-ai: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
