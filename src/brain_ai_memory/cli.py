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
    parser = argparse.ArgumentParser(prog="brain-ai", description="Installable Brain-AI memory lifecycle runtime")
    parser.add_argument("--home", help="runtime directory (default: $BRAIN_AI_HOME or ./.brain-ai)")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    init = sub.add_parser("init", help="initialize a local runtime")
    init.add_argument("--json", action="store_true")

    remember = sub.add_parser("remember", help="write to a differentiated memory store")
    remember.add_argument("--type", choices=("episodic", "semantic", "rule", "state"), required=True)
    remember.add_argument("--text")
    remember.add_argument("--source", default="cli")
    remember.add_argument("--tags", nargs="*", default=[])
    remember.add_argument("--promote", choices=("semantic", "rule"))
    remember.add_argument("--pattern", help="regular expression for a procedural rule")
    remember.add_argument("--effect", choices=("block", "warn"), default="block")
    remember.add_argument("--key")
    remember.add_argument("--value")
    remember.add_argument("--json", action="store_true")

    recall = sub.add_parser("recall", help="route and retrieve component-specific memory")
    recall.add_argument("query")
    recall.add_argument("--action")
    recall.add_argument("--limit", type=int)
    recall.add_argument("--json", action="store_true")

    run = sub.add_parser("run", help="prepare an auditable context bundle for any executor")
    run.add_argument("query")
    run.add_argument("--action")
    run.add_argument("--limit", type=int)
    run.add_argument("--json", action="store_true")

    harness = sub.add_parser("harness", help="guard and run an explicit command without a shell")
    harness.add_argument("--query", required=True)
    harness.add_argument("--timeout", type=float, default=60)
    harness.add_argument("--cwd")
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

    lifecycle = sub.add_parser("lifecycle", help="apply one of seven lifecycle operations")
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

    demo = sub.add_parser("demo", help="run an end-to-end local demonstration")
    demo.add_argument("--json", action="store_true")
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
    }
    checks["ready"] = checks["home_exists"] and checks["database_exists"]
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
                    promote_to=args.promote, rule_pattern=args.pattern,
                )
            elif args.type == "semantic":
                if not args.text:
                    raise ValueError("--text is required for semantic memory")
                value = runtime.store.put_knowledge(args.text, source=args.source, tags=args.tags)
            elif args.type == "rule":
                if not args.pattern or not args.text:
                    raise ValueError("--pattern and --text (reason) are required for rule memory")
                value = runtime.store.add_rule(args.pattern, effect=args.effect, reason=args.text, source=args.source)
            else:
                if not args.key:
                    raise ValueError("--key is required for state memory")
                value = runtime.store.set_state(args.key, parse_value(args.value), source=args.source)
            emit(value, args.json)
        elif args.subcommand == "recall":
            emit(runtime.recall(args.query, limit=args.limit, proposed_action=args.action), args.json)
        elif args.subcommand == "run":
            emit(runtime.process(args.query, proposed_action=args.action, limit=args.limit), args.json)
        elif args.subcommand == "harness":
            command = args.command[1:] if args.command[:1] == ["--"] else args.command
            emit(runtime.execute(args.query, command, timeout=args.timeout, cwd=args.cwd), args.json)
        elif args.subcommand == "sequence":
            steps = []
            for raw in args.step:
                step = json.loads(raw)
                if not isinstance(step, list) or not step or not all(isinstance(item, str) for item in step):
                    raise ValueError("each --step must be a non-empty JSON array of strings")
                steps.append(step)
            emit(runtime.execute_sequence(args.query, steps, timeout=args.timeout, cwd=args.cwd), args.json)
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
        return 0
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"brain-ai: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
