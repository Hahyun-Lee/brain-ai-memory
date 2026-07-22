"""Previewable, owned lifecycle-hook wiring for supported agent hosts."""

from __future__ import annotations

import contextlib
import difflib
import json
import os
import shlex
import sys
from collections import Counter
from pathlib import Path

from . import __version__
from .storage import MemoryStore, utc_now
from .workspace import (
    WorkflowConflict,
    _atomic_bytes,
    _atomic_bytes_at,
    _digest,
    _pinned_config_parent,
    _read_config_at,
    _read_pinned_config,
    _workflow_lock,
    _workflow_root,
    connection_change,
    connection_status,
    entity_references_match,
)


INTEGRATION_SCHEMA = 2


def _binding_path(home: Path, host: str, root: Path) -> Path:
    return home / "integrations" / f"{host}-{_digest(str(root))[:12]}.json"


def _hook_path(host: str, root: Path) -> Path:
    if host == "codex":
        return root / ".codex" / "hooks.json"
    if host == "claude-code":
        return root / ".claude" / "settings.local.json"
    raise ValueError("host must be codex or claude-code")


def _load_object(text: str, path: Path) -> dict:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"refusing to edit invalid JSON config: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"config root must be an object: {path}")
    return value


def _hook_command(binding: Path) -> tuple[str, list[str], str]:
    command = os.path.abspath(sys.executable)
    args = ["-m", "brain_ai_memory.hook_cli", "--binding", str(binding)]
    if os.name == "nt":  # pragma: no cover - Windows generation
        import subprocess

        shell_command = subprocess.list2cmdline([command, *args])
    else:
        shell_command = shlex.join([command, *args])
    return command, args, shell_command


def _handler(host: str, binding: Path, timeout: int) -> dict:
    command, args, shell_command = _hook_command(binding)
    if host == "codex":
        return {"type": "command", "command": shell_command, "timeout": timeout}
    return {"type": "command", "command": command, "args": args, "timeout": timeout}


def _managed_groups(host: str, binding: Path) -> dict[str, list[dict]]:
    lifecycle = {
        "SessionStart": ("startup|resume|clear|compact", 10),
        "UserPromptSubmit": (None, 10),
        "PreToolUse": ("^Bash$", 8),
        "PostToolUse": (
            r"^(?:apply_patch|mcp__brain(?:-ai-memory|_ai_memory)__(?:brain_remember|brain_checkpoint|brain_supersede))$"
            if host == "codex"
            else r"^(?:Edit|Write|MultiEdit|NotebookEdit|mcp__brain(?:-ai-memory|_ai_memory)__(?:brain_remember|brain_checkpoint|brain_supersede))$",
            10,
        ),
        "PreCompact": ("manual|auto", 10),
        "Stop": (None, 10),
    }
    if host == "claude-code":
        lifecycle["SessionEnd"] = (None, 8)
    groups: dict[str, list[dict]] = {}
    for event, (matcher, timeout) in lifecycle.items():
        group = {"hooks": [_handler(host, binding, timeout)]}
        if matcher:
            group["matcher"] = matcher
        groups[event] = [group]
    return groups


def _group_contains_binding(group: object, binding: Path) -> bool:
    if not isinstance(group, dict):
        return False
    marker = str(binding)
    for handler in group.get("hooks", []):
        if isinstance(handler, dict) and marker in json.dumps(handler, ensure_ascii=False):
            return True
    return False


def _merge_hooks(
    before: str,
    *,
    path: Path,
    host: str,
    binding: Path,
    disconnect: bool,
    binding_record: dict | None,
) -> tuple[str, dict]:
    config = _load_object(before, path)
    expected = _managed_groups(host, binding)
    if disconnect and not binding_record:
        hooks = config.get("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be an object")
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                raise ValueError(f"hooks.{event} must be an array")
            if any(_group_contains_binding(group, binding) for group in groups):
                raise ValueError(
                    "a lifecycle hook references this binding without an ownership record"
                )
        return before, {
            "events": sorted(expected),
            "handler_count": sum(len(groups) for groups in expected.values()),
            "managed_hooks": {
                event: [_digest(group) for group in groups]
                for event, groups in sorted(expected.items())
            },
        }
    hooks = config.get("hooks")
    if hooks is None:
        hooks = {}
        config["hooks"] = hooks
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    owned_hooks = (binding_record or {}).get("managed_hooks", {})
    if not isinstance(owned_hooks, dict) or any(
        not isinstance(event, str)
        or not isinstance(digests, list)
        or not all(isinstance(digest, str) for digest in digests)
        for event, digests in owned_hooks.items()
    ):
        raise ValueError("lifecycle binding has invalid managed hook ownership")
    expected_receipts = Counter(
        (event, digest)
        for event, digests in owned_hooks.items()
        for digest in digests
    )
    observed_receipts: Counter[tuple[str, str]] = Counter()

    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            raise ValueError(f"hooks.{event} must be an array")
        retained = []
        for group in groups:
            digest = _digest(group) if isinstance(group, dict) else ""
            if _group_contains_binding(group, binding):
                receipt = (event, digest)
                if not expected_receipts:
                    raise ValueError(
                        "a lifecycle hook references this binding without an ownership record"
                    )
                observed_receipts[receipt] += 1
                if observed_receipts[receipt] > expected_receipts[receipt]:
                    raise ValueError("managed lifecycle hook was modified; refusing to replace or remove it")
                # Remove the owned definition before either disconnecting or
                # adding the current package definition.  This permits an
                # intentional package upgrade while still rejecting tampering.
                continue
            retained.append(group)
        hooks[event] = retained
        if not retained:
            hooks.pop(event, None)

    if expected_receipts and observed_receipts != expected_receipts:
        raise ValueError("one or more managed lifecycle hooks are missing or modified")
    if not disconnect:
        for event, groups in expected.items():
            hooks.setdefault(event, []).extend(groups)

    if not hooks:
        config.pop("hooks", None)
    after = json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    summary = {
        "events": sorted(expected),
        "handler_count": sum(len(groups) for groups in expected.values()),
        "managed_hooks": {
            event: [_digest(group) for group in groups]
            for event, groups in sorted(expected.items())
        },
    }
    return after, summary


def _sanitized_diff(path: Path, before: dict, after: dict) -> str:
    old = json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    new = json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{path} (Brain-AI hooks only)",
            tofile=f"{path} (Brain-AI hooks only)",
        )
    )


def _unlink_at(path: Path, parent_descriptor: int | None, *, available: bool) -> None:
    if not available:
        return
    if parent_descriptor is None:  # pragma: no cover - non-POSIX fallback
        path.unlink(missing_ok=True)
        return
    try:
        os.unlink(path.name, dir_fd=parent_descriptor)
        os.fsync(parent_descriptor)
    except FileNotFoundError:
        pass


def _file_change_needed(
    before: str,
    before_mode: int | None,
    after: str | None,
) -> bool:
    if after is None:
        return before_mode is not None
    return before_mode is None or after != before


def _empty_managed_mcp_config(host: str, text: str, path: Path) -> bool:
    if host == "codex":
        return not text.strip()
    config = _load_object(text, path)
    return config in ({}, {"mcpServers": {}})


def _apply_file_changes(home: Path, changes: list[dict], lock_key: str) -> None:
    selected = [change for change in changes if change["changed"]]
    if not selected:
        return
    with _workflow_lock(home, lock_key):
        with contextlib.ExitStack() as stack:
            opened = []
            for change in selected:
                parent_descriptor, available = stack.enter_context(
                    _pinned_config_parent(
                        change["path"], change["config_root"], create=True
                    )
                )
                current, current_mode = _read_config_at(
                    change["path"], parent_descriptor, available=available
                )
                current_exists = current_mode is not None
                if current != change["before"] or current_exists != change["before_exists"]:
                    raise WorkflowConflict(
                        "config_changed: preview the lifecycle integration again"
                    )
                opened.append((change, parent_descriptor, available, current_mode))

            written = []
            try:
                for change, descriptor, available, current_mode in opened:
                    if change["before_exists"] and change.get("backup", True):
                        backup = (
                            _workflow_root(home)
                            / "config-backups"
                            / f"loop-{change['path'].name}-{_digest(change['before'])[:12]}.bak"
                        )
                        if not backup.exists():
                            _atomic_bytes(backup, change["before"].encode("utf-8"))
                    if change["after"] is None:
                        _unlink_at(change["path"], descriptor, available=available)
                    else:
                        write_mode = (
                            current_mode
                            if change.get("preserve_mode", True) and current_mode is not None
                            else change["mode"]
                        )
                        _atomic_bytes_at(
                            change["path"],
                            change["after"].encode("utf-8"),
                            mode=write_mode,
                            parent_descriptor=descriptor,
                        )
                    written.append((change, descriptor, available, current_mode))

                for change, descriptor, available, _ in opened:
                    verified, verified_mode = _read_config_at(
                        change["path"], descriptor, available=available
                    )
                    expected = "" if change["after"] is None else change["after"]
                    expected_exists = change["after"] is not None
                    if verified != expected or (verified_mode is not None) != expected_exists:
                        raise WorkflowConflict(
                            "config_changed: lifecycle integration verification failed"
                        )
                    if (
                        expected_exists
                        and not change.get("preserve_mode", True)
                        and os.name == "posix"
                        and verified_mode != change["mode"]
                    ):
                        raise WorkflowConflict(
                            "config_changed: lifecycle binding permissions are unsafe"
                        )
            except Exception:
                for change, descriptor, available, current_mode in reversed(written):
                    if change["before_exists"]:
                        _atomic_bytes_at(
                            change["path"],
                            change["before"].encode("utf-8"),
                            mode=current_mode or change["mode"],
                            parent_descriptor=descriptor,
                        )
                    else:
                        _unlink_at(change["path"], descriptor, available=available)
                raise


def lifecycle_connection_change(
    home: Path,
    host: str,
    *,
    entity: str,
    project_root: str | Path,
    disconnect: bool = False,
    apply: bool = False,
    mcp_file_created: bool | None = None,
) -> dict:
    home = Path(home).expanduser().resolve()
    if host not in {"codex", "claude-code"}:
        raise ValueError("host must be codex or claude-code")
    if not disconnect and not entity.strip():
        raise ValueError("--entity is required for autonomous loop wiring")
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")
    hook_path = _hook_path(host, root)
    binding_path = _binding_path(home, host, root)
    hook_before, hook_mode = _read_pinned_config(hook_path, root)
    if home.is_dir():
        binding_before, binding_mode = _read_pinned_config(binding_path, home)
    else:
        # A preview must remain read-only and may run before the runtime exists.
        binding_before, binding_mode = "", None
    binding_record = _load_object(binding_before, binding_path) if binding_before else None
    effective_entity = entity.strip()
    owned_mcp_file_created = bool(
        (binding_record or {}).get("mcp_file_created", bool(mcp_file_created))
    )
    if binding_record:
        if binding_record.get("schema_version") != INTEGRATION_SCHEMA:
            raise ValueError("unsupported lifecycle binding version")
        if binding_record.get("home") != str(home) or binding_record.get("host") != host:
            raise ValueError("lifecycle binding belongs to a different runtime")
        if binding_record.get("project_root") != str(root):
            raise ValueError("lifecycle binding belongs to a different project")
        configured_entity = str(binding_record.get("entity") or "")
        if effective_entity and not entity_references_match(
            home, configured_entity, effective_entity
        ):
            raise ValueError("lifecycle binding belongs to a different entity; disconnect it first")
        if effective_entity:
            # Preserve the existing label when the caller used an alias for the
            # same stable entity. This avoids rewriting an otherwise identical
            # binding and resetting its activity window.
            effective_entity = configured_entity

    hook_after, summary = _merge_hooks(
        hook_before,
        path=hook_path,
        host=host,
        binding=binding_path,
        disconnect=disconnect,
        binding_record=binding_record,
    )
    if disconnect and hook_mode is None and not hook_after:
        hook_after_value = None
    elif disconnect and binding_record and binding_record.get("hook_file_created") and _load_object(hook_after, hook_path) == {}:
        hook_after_value: str | None = None
    else:
        hook_after_value = hook_after
    if disconnect:
        binding_after: str | None = None
    else:
        now = utc_now()
        binding = {
            "schema_version": INTEGRATION_SCHEMA,
            "package_version": __version__,
            "host": host,
            "home": str(home),
            "entity": effective_entity,
            "project_root": str(root),
            "python": os.path.abspath(sys.executable),
            "hook_config": str(hook_path),
            "hook_file_created": (binding_record or {}).get(
                "hook_file_created", hook_mode is None
            ),
            "mcp_file_created": (binding_record or {}).get(
                "mcp_file_created", bool(mcp_file_created)
            ),
            "managed_hooks": summary["managed_hooks"],
            "capture_policy": {
                "raw_prompt": False,
                "raw_tool_output": False,
                "artifact_paths": True,
                "semantic_promotion": "review-only",
            },
            "created_at": (binding_record or {}).get("created_at", now),
            "updated_at": (binding_record or {}).get("updated_at", now),
        }
        if binding_record:
            old_comparable = {
                key: value for key, value in binding_record.items() if key != "updated_at"
            }
            new_comparable = {
                key: value for key, value in binding.items() if key != "updated_at"
            }
            if old_comparable != new_comparable:
                binding["updated_at"] = now
        binding_after = json.dumps(binding, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    changes = [
        {
            "path": hook_path,
            "config_root": root,
            "before": hook_before,
            "before_exists": hook_mode is not None,
            "after": hook_after_value,
            "mode": 0o644,
            "changed": _file_change_needed(
                hook_before, hook_mode, hook_after_value
            ),
            "backup": True,
            "preserve_mode": True,
        },
        {
            "path": binding_path,
            "config_root": home,
            "before": binding_before,
            "before_exists": binding_mode is not None,
            "after": binding_after,
            "mode": 0o600,
            "changed": (
                _file_change_needed(binding_before, binding_mode, binding_after)
                or (
                    binding_after is not None
                    and binding_mode is not None
                    and os.name == "posix"
                    and binding_mode != 0o600
                )
            ),
            "backup": False,
            "preserve_mode": False,
        },
    ]
    changed = any(item["changed"] for item in changes)
    if apply:
        _apply_file_changes(home, changes, f"lifecycle:{host}:{root}")
    before_summary = {
        "binding": "present" if binding_before else "absent",
        "events": sorted((binding_record or {}).get("managed_hooks", {})),
    }
    after_summary = {
        "binding": "absent" if disconnect else "present",
        "events": [] if disconnect else summary["events"],
        "mcp_file_created": owned_mcp_file_created,
    }
    return {
        "host": host,
        "entity": None if disconnect else effective_entity,
        "project_root": str(root),
        "hook_config": str(hook_path),
        "binding": str(binding_path),
        "status": "disconnected" if disconnect and apply else ("configured" if apply else "preview"),
        "changed": changed,
        "applied": apply,
        "diff": _sanitized_diff(hook_path, before_summary, after_summary),
        "host_trust": "required" if host == "codex" and not disconnect else "workspace",
        "events": [] if disconnect else summary["events"],
        "mcp_file_created": owned_mcp_file_created,
    }


def lifecycle_connection_status(
    home: Path,
    host: str,
    *,
    entity: str | None,
    project_root: str | Path,
) -> dict:
    home = Path(home).expanduser().resolve()
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")
    hook_path = _hook_path(host, root)
    binding_path = _binding_path(home, host, root)
    error = None
    configured = False
    binding = None
    observed_events: list[dict] = []
    active = False
    active_last_seen = None
    loop_error = None
    source_freshness: list[dict] = []
    source_attention_count = 0
    stale_source_record_count = 0
    try:
        hook_text, _ = _read_pinned_config(hook_path, root)
        binding_text, binding_mode = _read_pinned_config(binding_path, home)
        binding = _load_object(binding_text, binding_path) if binding_text else None
        if binding:
            if os.name == "posix" and binding_mode != 0o600:
                raise ValueError("lifecycle binding permissions must be 0600")
            if entity is not None and not entity_references_match(
                home, str(binding.get("entity") or ""), entity
            ):
                raise ValueError("configured loop entity does not match")
            expected = _managed_groups(host, binding_path)
            config = _load_object(hook_text, hook_path)
            hooks = config.get("hooks", {})
            configured = all(
                any(group in hooks.get(event, []) for group in groups)
                for event, groups in expected.items()
            )
            runtime_home = Path(binding["home"])
            from .runtime import BrainAIRuntime
            from .loop import LoopLedger

            runtime = BrainAIRuntime(runtime_home)
            entity_id = runtime.store.get_entity(binding["entity"])["id"]
            loop_status = LoopLedger(runtime).status(
                host=host,
                entity_id=entity_id,
                since=binding["updated_at"],
            )
            observed_events = loop_status["observed_events"]
            active = bool(loop_status["active"])
            active_last_seen = loop_status["active_last_seen"]
            source_freshness = loop_status.get("source_freshness", [])
            source_attention_count = int(
                loop_status.get("source_attention_count", 0)
            )
            stale_source_record_count = int(
                loop_status.get("stale_source_record_count", 0)
            )
            if not active and loop_status.get("event_issues"):
                issue = loop_status["event_issues"][0]
                loop_error = (
                    f"{issue['event_name']} is {issue['status']}"
                    + (f": {issue['error']}" if issue.get("error") else "")
                )[:240]
            elif not active and loop_status.get("sessions"):
                latest_error = loop_status["sessions"][0].get("last_error")
                if latest_error:
                    loop_error = str(latest_error)[:240]
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        error = " ".join(str(exc).split())[:240]
    if not binding:
        active = False
        active_last_seen = None
    observed_names = {item["event_name"] for item in observed_events}
    return {
        "host": host,
        "hook_config": str(hook_path),
        "binding": str(binding_path),
        "configured": configured,
        "configured_entity": binding.get("entity") if binding else None,
        "observed_events": observed_events,
        "active": configured and active,
        "active_last_seen": active_last_seen,
        "loop_error": loop_error,
        "source_freshness": source_freshness,
        "source_attention_count": source_attention_count,
        "stale_source_record_count": stale_source_record_count,
        "host_trust": "observed" if observed_events else ("required" if host == "codex" else "unknown"),
        "session_end_support": (
            "observed"
            if host == "claude-code" and "SessionEnd" in observed_names
            else (
                "configured"
                if host == "claude-code" and configured
                else ("unsupported" if host == "codex" else "not_configured")
            )
        ),
        "error": error,
    }


def loop_connection_change(
    home: Path,
    host: str,
    *,
    entity: str,
    scope: str = "project",
    project_root: str | Path = ".",
    disconnect: bool = False,
    apply: bool = False,
) -> dict:
    home = Path(home).expanduser().resolve()
    if scope != "project":
        raise ValueError("autonomous loop mode currently supports project scope only")
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")
    mcp_before = connection_status(
        home, host, scope=scope, project_root=root, entity=None
    )
    lifecycle_before = lifecycle_connection_status(
        home, host, entity=None, project_root=root
    )
    effective_entity = entity.strip()
    if disconnect and not effective_entity:
        effective_entity = str(
            mcp_before.get("configured_entity")
            or lifecycle_before.get("configured_entity")
            or ""
        ).strip()
    if not effective_entity:
        raise ValueError("--entity is required and no managed project entity was found")
    configured_reference = str(
        mcp_before.get("configured_entity")
        or lifecycle_before.get("configured_entity")
        or ""
    ).strip()
    if configured_reference and entity_references_match(
        home, configured_reference, effective_entity
    ):
        effective_entity = configured_reference
    if (
        not disconnect
        and mcp_before.get("managed_entry")
        and not entity_references_match(
            home,
            str(mcp_before.get("configured_entity") or ""),
            effective_entity,
        )
    ):
        raise ValueError("managed connection uses another entity; disconnect it before enabling loop mode")
    if apply and not disconnect:
        quarantined_rules = MemoryStore(home).applicable_rule_quarantines(
            effective_entity
        )
        if quarantined_rules:
            raise ValueError(
                "cannot enable autonomous loop while "
                f"{len(quarantined_rules)} applicable legacy rule(s) require review; "
                f"run brain-ai --home {shlex.quote(str(home))} rule list --json, "
                "create safe replacements with brain-ai remember --type rule, then "
                "acknowledge each old rule with brain-ai rule disable RULE_ID --yes"
            )
    mcp = connection_change(
        home,
        host,
        entity=effective_entity,
        scope=scope,
        project_root=root,
        disconnect=disconnect,
        apply=False,
    )
    lifecycle = lifecycle_connection_change(
        home,
        host,
        entity=effective_entity,
        project_root=root,
        disconnect=disconnect,
        apply=False,
    )
    if apply:
        mcp_mutated = False
        mcp_path = Path(mcp["path"])
        mcp_before_text = ""
        mcp_before_mode: int | None = None
        mcp_after_text = ""
        mcp_after_mode: int | None = None
        try:
            mcp = connection_change(
                home,
                host,
                entity=effective_entity,
                scope=scope,
                project_root=root,
                disconnect=disconnect,
                apply=True,
                _transaction_details=True,
            )
            transaction = mcp.pop("_transaction")
            mcp_before_text = transaction["before"]
            mcp_before_mode = transaction["before_mode"]
            mcp_after_text = transaction["after"]
            mcp_after_mode = transaction["after_mode"]
            mcp_mutated = mcp["changed"]
            owned_mcp_file = bool(lifecycle.get("mcp_file_created"))
            if (
                disconnect
                and owned_mcp_file
                and mcp_after_mode is not None
                and _empty_managed_mcp_config(host, mcp_after_text, mcp_path)
            ):
                _apply_file_changes(
                    home,
                    [
                        {
                            "path": mcp_path,
                            "config_root": root,
                            "before": mcp_after_text,
                            "before_exists": True,
                            "after": None,
                            "mode": mcp_after_mode or 0o644,
                            "changed": True,
                            "backup": False,
                            "preserve_mode": False,
                        }
                    ],
                    f"loop-mcp-cleanup:{host}:{root}",
                )
                mcp_after_text = ""
                mcp_after_mode = None
                mcp_mutated = True
            lifecycle = lifecycle_connection_change(
                home,
                host,
                entity=effective_entity,
                project_root=root,
                disconnect=disconnect,
                apply=True,
                mcp_file_created=(
                    not disconnect and mcp_before_mode is None
                ),
            )
        except Exception:
            if mcp_mutated:
                try:
                    _apply_file_changes(
                        home,
                        [
                            {
                                "path": mcp_path,
                                "config_root": root,
                                "before": mcp_after_text,
                                "before_exists": mcp_after_mode is not None,
                                "after": (
                                    mcp_before_text
                                    if mcp_before_mode is not None
                                    else None
                                ),
                                "mode": mcp_before_mode or 0o644,
                                "changed": True,
                                "backup": False,
                                "preserve_mode": False,
                            }
                        ],
                        f"loop-mcp-rollback:{host}:{root}",
                    )
                except Exception as rollback_exc:
                    raise WorkflowConflict(
                        "lifecycle setup failed and the previous host connection "
                        "could not be restored; inspect the project host config"
                    ) from rollback_exc
            raise
    changed = bool(mcp["changed"] or lifecycle["changed"])
    action = "disconnect" if disconnect else "connect"
    next_command = None
    if not apply and changed:
        next_command = (
            f"brain-ai --home {shlex.quote(str(home))} {action} {host} "
            f"--entity {shlex.quote(effective_entity)} --mode loop "
            f"--project-root {shlex.quote(str(root))} --apply"
        )
    return {
        "host": host,
        "scope": scope,
        "mode": "loop",
        "entity": None if disconnect else effective_entity,
        "status": "disconnected" if disconnect and apply else ("configured" if apply else "preview"),
        "changed": changed,
        "applied": apply,
        "diff": mcp["diff"] + lifecycle["diff"],
        "next": next_command,
        "mcp": mcp,
        "lifecycle": lifecycle,
    }


def loop_connection_status(
    home: Path,
    host: str,
    *,
    entity: str | None,
    scope: str,
    project_root: str | Path,
) -> dict:
    home = Path(home).expanduser().resolve()
    if scope != "project":
        raise ValueError("autonomous loop mode currently supports project scope only")
    mcp = connection_status(
        home, host, scope=scope, project_root=project_root, entity=entity
    )
    lifecycle = lifecycle_connection_status(
        home, host, entity=entity, project_root=project_root
    )
    return {
        "mode": "loop",
        "mcp": mcp,
        "lifecycle": lifecycle,
        "configured": bool(mcp["configured"] and lifecycle["configured"]),
        "active": bool(mcp["configured"] and lifecycle["active"]),
    }
