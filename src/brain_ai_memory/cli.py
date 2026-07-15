"""brain-ai command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import resolve_home
from .control import serve
from .runtime import BrainAIRuntime
from .storage import LIFECYCLE_OPERATIONS


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
    sub = parser.add_subparsers(dest="subcommand", required=True)

    init = sub.add_parser("init", help="initialize a local runtime")
    init.add_argument("--json", action="store_true")

    remember = sub.add_parser("remember", help="write to a differentiated memory store")
    remember.add_argument("--type", choices=("episodic", "semantic", "rule", "state"), required=True)
    remember.add_argument("--text")
    remember.add_argument("--source", default="cli")
    remember.add_argument("--tags", nargs="*", default=[])
    remember.add_argument("--entity", action="append", default=[], help="entity id, name, or alias; repeatable")
    remember.add_argument("--promote", choices=("semantic", "rule"))
    remember.add_argument("--pattern", help="regular expression for a procedural rule")
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

    consolidate = sub.add_parser("consolidate", help="preview or apply episodic promotion")
    consolidate.add_argument("--apply", action="store_true", help="apply approved candidates; default is preview")
    consolidate.add_argument("--json", action="store_true")

    supersede = sub.add_parser("supersede", help="reconsolidate stale semantic memory")
    supersede.add_argument("old_id")
    supersede.add_argument("--text", required=True)
    supersede.add_argument("--source", default="cli")
    supersede.add_argument("--tags", nargs="*", default=[])
    supersede.add_argument("--json", action="store_true")

    lifecycle = sub.add_parser("lifecycle", help="record one of seven lifecycle decisions")
    lifecycle.add_argument("target_type", choices=("episodic", "semantic"))
    lifecycle.add_argument("target_id")
    lifecycle.add_argument("operation", choices=sorted(LIFECYCLE_OPERATIONS))
    lifecycle.add_argument("--reason", default="")
    lifecycle.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="show component counts and runtime health")
    status.add_argument("--json", action="store_true")

    doctor = sub.add_parser("doctor", help="check local configuration and adapter readiness")
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
    return parser


def parse_value(value: str | None):
    if value is None:
        raise ValueError("--value is required for state memory")
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def doctor(runtime: BrainAIRuntime) -> dict:
    semantic = runtime.config.get("semantic", {})
    vault = semantic.get("vault_path")
    command = semantic.get("mcp_command") or []
    checks = {
        "home_exists": runtime.home.is_dir(),
        "database_exists": runtime.store.db_path.is_file(),
        "semantic_backend": semantic.get("backend", "local"),
        "vault_exists": None if not vault else Path(vault).expanduser().is_dir(),
        "mcp_command_configured": bool(command),
        "ontology_valid": runtime.ontology_summary["component_count"] > 0,
    }
    checks["ready"] = (
        checks["home_exists"]
        and checks["database_exists"]
        and checks["ontology_valid"]
    )
    return checks


def run_demo(runtime: BrainAIRuntime) -> dict:
    knowledge = runtime.store.put_knowledge(
        "Atlas releases require a completed review before deployment.", source="demo", tags=["release"]
    )
    runtime.store.set_state("atlas_open_reviews", 3, source="demo")
    existing = [rule for rule in runtime.store.rules() if rule["source"] == "demo"]
    rule = existing[0] if existing else runtime.store.add_rule(
        r"deploy\s+atlas", effect="warn", reason="confirm that the release review is complete", source="demo"
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
            r"deploy\s+production",
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
    checkpoint = runtime.checkpoint("local tour completed")
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = BrainAIRuntime(resolve_home(args.home))
    try:
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
        elif args.subcommand == "consolidate":
            emit(runtime.consolidate(apply=args.apply), args.json)
        elif args.subcommand == "supersede":
            emit(runtime.reconsolidate(args.old_id, args.text, source=args.source, tags=args.tags), args.json)
        elif args.subcommand == "lifecycle":
            emit(runtime.store.record_lifecycle(args.target_type, args.target_id, args.operation, args.reason), args.json)
        elif args.subcommand == "status":
            emit(runtime.status(), args.json)
        elif args.subcommand == "doctor":
            emit(doctor(runtime), args.json)
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
                runtime.home, host=args.host, port=args.port
            )
            server.run(transport=args.transport)
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"brain-ai: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
