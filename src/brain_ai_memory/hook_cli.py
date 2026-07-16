"""Host hook entry point for the supervised autonomous memory loop."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .loop import LoopCoordinator, SUPPORTED_HOSTS, _error_reference
from .runtime import BrainAIRuntime


MAX_HOOK_INPUT_BYTES = 2 * 1024 * 1024
MAX_BINDING_BYTES = 64 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brain-ai-hook")
    parser.add_argument("--binding", help="private integration binding written by brain-ai connect")
    parser.add_argument("--home")
    parser.add_argument("--host", choices=sorted(SUPPORTED_HOSTS))
    parser.add_argument("--entity")
    parser.add_argument("--project-root")
    return parser


def _read_binding(path: str | Path) -> dict:
    selected = Path(path).expanduser()
    if not selected.is_absolute():
        raise ValueError("hook binding path must be absolute")
    info = selected.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("hook binding must be a regular, non-symbolic-link file")
    if info.st_size > MAX_BINDING_BYTES:
        raise ValueError("hook binding is too large")
    if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("hook binding must not be accessible by group or other users")
    value = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise ValueError("unsupported hook binding")
    for key in ("home", "host", "entity", "project_root"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise ValueError(f"hook binding is missing {key}")
    return value


def _configuration(args: argparse.Namespace) -> dict:
    if args.binding:
        binding = _read_binding(args.binding)
        if args.host and args.host != binding["host"]:
            raise ValueError("--host does not match the hook binding")
        return binding
    values = {
        "home": args.home,
        "host": args.host,
        "entity": args.entity,
        "project_root": args.project_root,
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError("missing hook configuration: " + ", ".join(missing))
    return {"schema_version": 2, **values}


def _read_input() -> dict:
    raw = sys.stdin.buffer.read(MAX_HOOK_INPUT_BYTES + 1)
    if len(raw) > MAX_HOOK_INPUT_BYTES:
        raise ValueError(f"hook input exceeds {MAX_HOOK_INPUT_BYTES} bytes")
    if not raw.strip():
        raise ValueError("hook input is empty")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def host_output(event_name: str | None, result: dict) -> dict:
    output: dict = {}
    if result.get("system_message"):
        output["systemMessage"] = result["system_message"]
    if result.get("blocked") and event_name == "PreToolUse":
        rule_id = str(result.get("rule_id") or "unknown")
        if not all(character.isalnum() or character in "_.:-" for character in rule_id):
            rule_id = "unknown"
        rule_id = rule_id[:96] or "unknown"
        output["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"Blocked by Brain-AI Memory procedural rule ({rule_id})."
            ),
        }
        return output
    context = result.get("context")
    if context and event_name in {"SessionStart", "UserPromptSubmit", "PreToolUse"}:
        output["hookSpecificOutput"] = {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    return output


def main(argv: list[str] | None = None) -> int:
    event_name = None
    try:
        args = _parser().parse_args(argv)
        config = _configuration(args)
        payload = _read_input()
        event_name = payload.get("hook_event_name")
        runtime = BrainAIRuntime(config["home"])
        coordinator = LoopCoordinator(
            runtime,
            host=config["host"],
            entity=config["entity"],
            project_root=config["project_root"],
        )
        output = host_output(event_name, coordinator.handle(payload))
    except Exception as exc:
        output = {
            "systemMessage": (
                "Brain-AI Memory loop unavailable; inspect local configuration "
                f"(error ref: {_error_reference(exc)})."
            )
        }
    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
