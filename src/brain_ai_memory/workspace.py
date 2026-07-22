"""Safe adoption workflow for existing Markdown memory files.

The workflow deliberately separates observation from mutation:

``audit`` reads one explicit Markdown file, ``review`` records human choices,
and ``apply`` imports only those choices into the local typed store.  The source
file is evidence and is never rewritten by this module.
"""

from __future__ import annotations

import contextlib
import difflib
import hashlib
import json
import os
import re
import shlex
import sqlite3
import stat
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from .storage import (
    MemoryStore,
    compile_safe_rule_pattern,
    new_id,
    utc_now,
    validate_rule_reason,
)
from .privacy import ensure_private_directory, open_private_lock


WORKFLOW_SCHEMA = 1
PARSER_VERSION = "markdown-memory-v2"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 100_000
MAX_TRACKED_IMPORT_SOURCES = 32
ALLOWED_DECISIONS = {"semantic", "episodic", "state", "rule", "skip", "supersede"}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_OPEN_RE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
FENCE_CLOSE_RE = re.compile(r"^\s{0,3}(?P<marker>`{3,}|~{3,})[ \t]*$")
LIST_RE = re.compile(r"^(\s*)(?:[-+*]|\d+[.)])\s+(.+)$")
KEY_VALUE_RE = re.compile(
    r"^(?:\*\*|__)?(?P<key>[A-Za-z0-9가-힣][A-Za-z0-9가-힣_ ./-]{0,79})"
    r"(?:\*\*|__)?\s*[:=]\s*(?P<value>\S.*)$"
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

EPISODIC_HEADINGS = {
    "event", "events", "history", "timeline", "session", "sessions", "log", "logs",
    "사건", "기록", "이력", "타임라인", "세션", "로그", "변경 이력",
}
RULE_HEADINGS = {
    "rule", "rules", "procedure", "procedures", "policy", "policies", "workflow",
    "instruction", "instructions", "규칙", "절차", "정책", "워크플로", "지침",
}
STATE_HEADINGS = {
    "state", "status", "metric", "metrics", "values", "current state",
    "상태", "현황", "수치", "현재 상태",
}


class WorkflowConflict(RuntimeError):
    """The reviewed preimage no longer matches the source or memory store."""


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: bytes | str | dict | list) -> str:
    if isinstance(value, (dict, list)):
        payload = _canonical_json(value).encode("utf-8")
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = value
    return hashlib.sha256(payload).hexdigest()


def _stable_id(prefix: str, value: dict | list | str) -> str:
    return f"{prefix}_{_digest(value)[:16]}"


def safe_display(value: str, limit: int = 180) -> str:
    """Return terminal-safe single-line text for human output."""
    clean = CONTROL_RE.sub("", value).replace("\n", " ").replace("\r", " ")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean if len(clean) <= limit else clean[: limit - 1] + "…"


def _open_directory_components(path: Path, flags: int) -> int:
    """Open an absolute canonical directory without following swapped components."""
    if not path.is_absolute():
        raise ValueError("pinned directory path must be absolute")
    parts = path.parts
    descriptor = os.open(path.anchor, flags)
    try:
        for component in parts[1:]:
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_markdown(
    path: str | Path,
    *,
    max_bytes: int = MAX_SOURCE_BYTES,
    allowed_root: str | Path | None = None,
) -> tuple[Path, bytes, str]:
    source = Path(os.path.abspath(Path(path).expanduser()))
    try:
        lexical_initial = source.lstat()
        if stat.S_ISLNK(lexical_initial.st_mode):
            raise ValueError("memory source must not be a symbolic link")
        if not stat.S_ISREG(lexical_initial.st_mode):
            raise ValueError("memory source must be a regular file")
        canonical_source = source.resolve(strict=True)
        canonical_initial = canonical_source.lstat()
    except OSError as exc:
        raise ValueError(f"cannot open memory source: {source}") from exc
    if (
        (lexical_initial.st_dev, lexical_initial.st_ino)
        != (canonical_initial.st_dev, canonical_initial.st_ino)
        or not stat.S_ISREG(canonical_initial.st_mode)
    ):
        raise ValueError("memory source changed while its path was being resolved")
    if allowed_root is not None:
        base = Path(allowed_root).expanduser().resolve(strict=True)
        if not canonical_source.is_relative_to(base):
            raise ValueError("memory source resolved outside the project root")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    parent_descriptor: int | None = None
    leaf_name: str | None = None
    try:
        if os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd:
            directory_flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            parent_descriptor = _open_directory_components(
                canonical_source.parent,
                directory_flags,
            )
            leaf_name = canonical_source.name
            initial = os.stat(
                leaf_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(initial.st_mode):
                raise ValueError("memory source must not be a symbolic link")
            if not stat.S_ISREG(initial.st_mode):
                raise ValueError("memory source must be a regular file")
            if (
                (canonical_initial.st_dev, canonical_initial.st_ino)
                != (initial.st_dev, initial.st_ino)
                or (canonical_initial.st_size, canonical_initial.st_mtime_ns)
                != (initial.st_size, initial.st_mtime_ns)
            ):
                raise ValueError("memory source changed while it was being opened")
            descriptor = os.open(leaf_name, flags, dir_fd=parent_descriptor)
        else:  # pragma: no cover - platforms without dir_fd support
            initial = canonical_source.lstat()
            if stat.S_ISLNK(initial.st_mode):
                raise ValueError("memory source must not be a symbolic link")
            if not stat.S_ISREG(initial.st_mode):
                raise ValueError("memory source must be a regular file")
            descriptor = os.open(canonical_source, flags)
    except ValueError:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise
    except OSError as exc:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        raise ValueError(
            f"cannot open memory source without following links: {source}"
        ) from exc
    try:
        if stat.S_ISLNK(initial.st_mode):
            raise ValueError("memory source must not be a symbolic link")
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("memory source must be a regular file")
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("memory source must be a regular file")
        if (initial.st_dev, initial.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError("memory source changed while it was being opened")
        if (initial.st_size, initial.st_mtime_ns) != (info.st_size, info.st_mtime_ns):
            raise ValueError("memory source changed while it was being opened")
        if info.st_size > max_bytes:
            raise ValueError(f"memory source exceeds {max_bytes} bytes")
        chunks = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        final_descriptor = os.fstat(descriptor)
        try:
            final_path = (
                os.stat(
                    leaf_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                if parent_descriptor is not None and leaf_name is not None
                else canonical_source.lstat()
            )
        except OSError as exc:
            raise ValueError("memory source changed while it was being read") from exc
        identity = (info.st_dev, info.st_ino)
        if (
            (final_descriptor.st_dev, final_descriptor.st_ino) != identity
            or (final_path.st_dev, final_path.st_ino) != identity
            or stat.S_ISLNK(final_path.st_mode)
            or (final_descriptor.st_size, final_descriptor.st_mtime_ns)
            != (info.st_size, info.st_mtime_ns)
        ):
            raise ValueError("memory source changed while it was being read")
    finally:
        os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    if len(raw) > max_bytes:
        raise ValueError(f"memory source exceeds {max_bytes} bytes")
    if b"\x00" in raw:
        raise ValueError("memory source contains NUL bytes")
    for line in raw.splitlines():
        if len(line) > MAX_LINE_BYTES:
            raise ValueError(f"memory source contains a line longer than {MAX_LINE_BYTES} bytes")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("memory source must be valid UTF-8 Markdown") from exc
    return canonical_source, raw, text


def discover_memory_file(root: str | Path = ".") -> Path:
    base = Path(root).expanduser().resolve()
    for candidate in (base / ".claude" / "MEMORY.md", base / "MEMORY.md"):
        try:
            relative = candidate.relative_to(base)
            current = base
            unsafe = False
            for part in relative.parts:
                current = current / part
                info = current.lstat()
                if stat.S_ISLNK(info.st_mode):
                    unsafe = True
                    break
            if not unsafe and stat.S_ISREG(candidate.lstat().st_mode):
                resolved = candidate.resolve(strict=True)
                if resolved.is_relative_to(base):
                    return resolved
        except (OSError, ValueError):
            continue
    raise ValueError("no memory file found; pass MEMORY.md explicitly")


def _normalize_entry(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()


def _clean_entry(lines: list[str]) -> str:
    if not lines:
        return ""
    first = LIST_RE.match(lines[0])
    values = [first.group(2) if first else lines[0], *lines[1:]]
    return _normalize_entry(" ".join(line.strip() for line in values))


def _heading_kind(headings: list[str], structured: dict | None) -> tuple[str, str]:
    lowered = " / ".join(headings).casefold()
    words = {part.strip() for part in re.split(r"[/›>:\-]", lowered) if part.strip()}
    words.update(re.findall(r"[a-z]+|[가-힣]+(?:\s+[가-힣]+)?", lowered))
    words.update(part for part in re.split(r"[^a-z가-힣]+", lowered) if part)
    if words & RULE_HEADINGS:
        return "rule", "needs_review"
    if words & STATE_HEADINGS:
        return ("state", "needs_review") if structured else ("semantic", "needs_review")
    if words & EPISODIC_HEADINGS:
        return "episodic", "ready"
    return "semantic", "ready"


def parse_markdown(
    text: str,
    source_path: Path,
    source_sha256: str,
    *,
    raw_bytes: bytes | None = None,
) -> list[dict]:
    """Parse inert, source-addressed Markdown entries without rendering links or HTML."""
    lines = text.splitlines()
    raw_lines = raw_bytes.splitlines(keepends=True) if raw_bytes is not None else None
    headings: list[str] = []
    ignored = [False] * len(lines)
    in_fence: tuple[str, int] | None = None
    in_comment = False
    in_blockquote = False
    in_frontmatter = bool(lines and lines[0].strip() == "---")

    for position, line in enumerate(lines):
        stripped = line.strip()
        if in_frontmatter:
            ignored[position] = True
            if position > 0 and stripped in {"---", "..."}:
                in_frontmatter = False
            continue
        if in_comment:
            ignored[position] = True
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line:
            ignored[position] = True
            if "-->" not in line.split("<!--", 1)[1]:
                in_comment = True
            continue
        if in_fence:
            ignored[position] = True
            closing = FENCE_CLOSE_RE.match(line)
            if (
                closing
                and closing.group("marker")[0] == in_fence[0]
                and len(closing.group("marker")) >= in_fence[1]
            ):
                in_fence = None
            continue
        fence = FENCE_OPEN_RE.match(line)
        if fence:
            ignored[position] = True
            marker = fence.group("marker")
            in_fence = (marker[0], len(marker))
            continue
        if in_blockquote:
            if stripped:
                ignored[position] = True
                continue
            in_blockquote = False
        if re.match(r"^\s{0,3}>", line):
            ignored[position] = True
            in_blockquote = True

    entries: list[dict] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if ignored[index] or not line.strip():
            index += 1
            continue
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            headings = headings[: level - 1] + [heading.group(2).strip()]
            index += 1
            continue
        if re.fullmatch(r"\s*[-:| ]+\s*", line):
            index += 1
            continue

        start = index
        block = [line]
        list_item = LIST_RE.match(line)
        index += 1
        while index < len(lines):
            current = lines[index]
            if ignored[index] or not current.strip() or HEADING_RE.match(current):
                break
            if list_item and LIST_RE.match(current):
                break
            if not list_item and LIST_RE.match(current):
                break
            block.append(current)
            index += 1

        cleaned = _clean_entry(block)
        if len(cleaned) < 3:
            continue
        structured = None
        match = KEY_VALUE_RE.match(cleaned)
        if match and match.group("key").casefold() not in {"http", "https"}:
            value = match.group("value").strip()
            if not value.startswith("//"):
                structured = {
                    "key": _normalize_entry(match.group("key")).strip("*_"),
                    "value": value,
                }
        suggested_type, status = _heading_kind(headings, structured)
        raw_text = "\n".join(block)
        fragment_payload = (
            b"".join(raw_lines[start : start + len(block)])
            if raw_lines is not None
            else raw_text.encode("utf-8")
        )
        fragment_sha = _digest(fragment_payload)
        identity = {
            "source": str(source_path),
            "source_sha256": source_sha256,
            "line_start": start + 1,
            "line_end": start + len(block),
            "fragment_sha256": fragment_sha,
        }
        entries.append(
            {
                "id": _stable_id("item", identity),
                "line_start": start + 1,
                "line_end": start + len(block),
                "heading": list(headings),
                "text": cleaned,
                "raw_text": raw_text,
                "fragment_sha256": fragment_sha,
                "fingerprint": _digest(identity),
                "structured": structured,
                "suggested_type": suggested_type,
                "status": status,
            }
        )
    return entries


def build_audit(path: str | Path | None, *, entity: str, root: str | Path = ".") -> dict:
    if not entity.strip():
        raise ValueError("--entity is required so imported memory cannot cross project scope")
    discovery_root = Path(root).expanduser().resolve() if path is None else None
    selected = discover_memory_file(discovery_root) if path is None else Path(path)
    source, raw, text = _read_markdown(selected, allowed_root=discovery_root)
    source_sha = _digest(raw)
    entries = parse_markdown(text, source, source_sha, raw_bytes=raw)
    findings: list[dict] = []

    duplicates: dict[str, list[dict]] = {}
    for entry in entries:
        duplicates.setdefault(_normalize_entry(entry["text"]), []).append(entry)
    for normalized, group in sorted(duplicates.items()):
        if len(group) < 2:
            continue
        original = group[0]
        for duplicate in group[1:]:
            duplicate["status"] = "duplicate_candidate"
            finding_identity = {
                "kind": "exact_duplicate_candidate",
                "first": original["id"],
                "duplicate": duplicate["id"],
                "normalized_sha256": _digest(normalized),
            }
            findings.append(
                {
                    "id": _stable_id("finding", finding_identity),
                    **finding_identity,
                    "reason": "normalized text is exactly equal; this does not judge truth",
                    "confidence": "deterministic",
                }
            )

    structured: dict[str, list[dict]] = {}
    for entry in entries:
        if entry["structured"]:
            key = unicodedata.normalize("NFC", entry["structured"]["key"]).casefold()
            structured.setdefault(key, []).append(entry)
    for key, group in sorted(structured.items()):
        values = {_normalize_entry(item["structured"]["value"]) for item in group}
        if len(values) < 2:
            continue
        for item in group:
            item["status"] = "needs_review"
        identity = {
            "kind": "possible_structured_conflict",
            "key": key,
            "candidate_ids": sorted(item["id"] for item in group),
            "literal_values": sorted(values),
        }
        findings.append(
            {
                "id": _stable_id("finding", identity),
                **identity,
                "reason": "the same explicit key has different literal values; no value is assumed current or true",
                "confidence": "deterministic-candidate",
            }
        )

    findings.sort(key=lambda finding: (finding["kind"], finding["id"]))
    counts = {
        "entries": len(entries),
        "ready": sum(item["status"] == "ready" for item in entries),
        "needs_review": sum(item["status"] == "needs_review" for item in entries),
        "duplicate_candidates": sum(
            item["kind"] == "exact_duplicate_candidate" for item in findings
        ),
        "possible_conflicts": sum(item["kind"] == "possible_structured_conflict" for item in findings),
    }
    entity_value = {"name": entity.strip(), "type": "project"}
    source_value = {
        "path": str(source),
        "sha256": source_sha,
        "size_bytes": len(raw),
    }
    identity = {
        "schema_version": WORKFLOW_SCHEMA,
        "parser_version": PARSER_VERSION,
        "entity": entity_value,
        "source": source_value,
        "counts": counts,
        "entries": entries,
        "findings": findings,
    }
    return {
        "schema_version": WORKFLOW_SCHEMA,
        "parser_version": PARSER_VERSION,
        "kind": "markdown-memory-audit",
        "id": _stable_id("audit", identity),
        "created_at": utc_now(),
        "entity": entity_value,
        "source": source_value,
        "counts": counts,
        "entries": entries,
        "findings": findings,
        "claims": {
            "source_changed": False,
            "memory_store_changed": False,
            "truth_or_currentness_inferred": False,
        },
    }


def _workflow_root(home: Path) -> Path:
    return home / "workflows"


def _private_directory(path: Path) -> None:
    ensure_private_directory(path)


def _protect_runtime_home(home: Path) -> None:
    _private_directory(home)
    ignore = home / ".gitignore"
    if not ignore.exists():
        _atomic_bytes(ignore, b"*\n", mode=0o600)


def _relative_fd_io_available() -> bool:
    return (
        os.name == "posix"
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
    )


def _atomic_bytes_at(
    path: Path,
    payload: bytes,
    *,
    mode: int,
    parent_descriptor: int | None,
) -> None:
    if parent_descriptor is None:  # pragma: no cover - non-POSIX fallback
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        temp_path = Path(temporary)
        try:
            if os.name == "posix":
                os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return

    temporary_name = f".{path.name}.{new_id('tmp')}.tmp"
    descriptor = os.open(
        temporary_name,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0),
        mode,
        dir_fd=parent_descriptor,
    )
    try:
        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        os.fsync(parent_descriptor)
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent_descriptor)
        except FileNotFoundError:
            pass


def _atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    _private_directory(path.parent)
    if not _relative_fd_io_available():
        _atomic_bytes_at(
            path,
            payload,
            mode=mode,
            parent_descriptor=None,
        )
        return
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    canonical_parent = path.parent.resolve(strict=True)
    parent_descriptor = _open_directory_components(
        canonical_parent,
        directory_flags,
    )
    try:
        _atomic_bytes_at(
            path,
            payload,
            mode=mode,
            parent_descriptor=parent_descriptor,
        )
    finally:
        os.close(parent_descriptor)


def _save_json(path: Path, value: dict) -> Path:
    _atomic_bytes(path, (_canonical_json(value) + "\n").encode("utf-8"))
    return path


def save_audit(home: Path, audit: dict) -> Path:
    _protect_runtime_home(home)
    directory = _workflow_root(home) / "audits"
    path = directory / f"{audit['id']}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable = (
            "schema_version", "parser_version", "kind", "id", "entity", "source",
            "counts", "entries", "findings", "claims",
        )
        if all(existing.get(key) == audit.get(key) for key in comparable):
            audit.clear()
            audit.update(existing)
            return path
    return _save_json(path, audit)


def inspect_source_freshness(
    home: Path,
    store: MemoryStore,
    *,
    entity: str,
    root: str | Path,
    save_changed_audits: bool = True,
) -> dict:
    """Compare approved import sources with their current project-local content.

    This is the prediction-error boundary for the automatic loop. It never
    promotes or replaces memory. Instead it identifies source-derived records
    whose exact fragment is no longer present, and optionally materializes an
    ordinary review audit for the new source version.
    """
    project_root = Path(root).expanduser().resolve(strict=True)
    if not project_root.is_dir():
        raise ValueError("source freshness root must be a directory")
    record_entity = store.get_entity(entity)
    entity_id = record_entity["id"]
    with store.connect() as conn:
        batches = conn.execute(
            """SELECT source_path, source_sha256, created_at
            FROM import_batches
            WHERE entity_id=? AND status='applied'
            ORDER BY created_at DESC, id DESC""",
            (entity_id,),
        ).fetchall()
        ledger_rows = conn.execute(
            """SELECT source_path, source_sha256, fragment_sha256,
                      memory_type, target_id, created_at
            FROM import_ledger
            WHERE entity_id=? AND status='active' AND target_id IS NOT NULL
            ORDER BY created_at, id""",
            (entity_id,),
        ).fetchall()

    latest_sources: dict[str, dict] = {}
    for row in batches:
        latest_sources.setdefault(row["source_path"], dict(row))
    ledger_by_source: dict[str, list[dict]] = {}
    for row in ledger_rows:
        ledger_by_source.setdefault(row["source_path"], []).append(dict(row))

    def target_map(rows: Iterable[dict]) -> dict[str, list[str]]:
        output = {"semantic": [], "episodic": [], "rule": [], "state": []}
        for row in rows:
            memory_type = (
                "semantic" if row.get("memory_type") == "supersede"
                else str(row.get("memory_type") or "")
            )
            target_id = row.get("target_id")
            if memory_type in output and target_id:
                output[memory_type].append(str(target_id))
        return {key: list(dict.fromkeys(values)) for key, values in output.items()}

    sources: list[dict] = []
    ordered_sources = list(latest_sources.items())
    for position, (source_path, batch) in enumerate(ordered_sources):
        source_rows = ledger_by_source.get(source_path, [])
        try:
            canonical = Path(source_path).expanduser().resolve(strict=True)
            display_path = canonical.relative_to(project_root).as_posix()
        except (OSError, ValueError):
            display_path = Path(source_path).name or "[unavailable-source]"
            sources.append(
                {
                    "path": source_path,
                    "display_path": display_path,
                    "status": "unavailable",
                    "applied_sha256": batch["source_sha256"],
                    "observed_sha256": None,
                    "stale_targets": target_map(source_rows),
                    "candidate_count": 0,
                    "audit_id": None,
                    "checked_at": utc_now(),
                }
            )
            continue
        if position >= MAX_TRACKED_IMPORT_SOURCES:
            sources.append(
                {
                    "path": str(canonical),
                    "display_path": display_path,
                    "status": "source-limit-exceeded",
                    "applied_sha256": batch["source_sha256"],
                    "observed_sha256": None,
                    "stale_targets": target_map(source_rows),
                    "candidate_count": 0,
                    "audit_id": None,
                    "checked_at": utc_now(),
                }
            )
            continue
        try:
            observed_path, observed_raw, _ = _read_markdown(
                canonical,
                allowed_root=project_root,
            )
            observed_sha = _digest(observed_raw)
            if observed_sha == batch["source_sha256"]:
                sources.append(
                    {
                        "path": str(observed_path),
                        "display_path": display_path,
                        "status": "current",
                        "applied_sha256": batch["source_sha256"],
                        "observed_sha256": observed_sha,
                        "stale_targets": target_map([]),
                        "candidate_count": 0,
                        "audit_id": None,
                        "checked_at": utc_now(),
                    }
                )
                continue

            audit = build_audit(
                observed_path,
                entity=record_entity["name"],
                root=project_root,
            )
            current_fragments = {
                item["fragment_sha256"] for item in audit["entries"]
            }
            imported_fragments = {
                str(row["fragment_sha256"]) for row in source_rows
            }
            current_target_keys = {
                (
                    "semantic" if row["memory_type"] == "supersede"
                    else row["memory_type"],
                    row["target_id"],
                )
                for row in source_rows
                if row["fragment_sha256"] in current_fragments
            }
            stale_rows = [
                row
                for row in source_rows
                if row["fragment_sha256"] not in current_fragments
                and (
                    "semantic" if row["memory_type"] == "supersede"
                    else row["memory_type"],
                    row["target_id"],
                ) not in current_target_keys
            ]
            candidate_count = sum(
                item["fragment_sha256"] not in imported_fragments
                for item in audit["entries"]
            )
            stale_targets = target_map(stale_rows)
            stale_count = sum(len(values) for values in stale_targets.values())
            audit_id = None
            status = "current-content"
            if stale_count or candidate_count:
                status = "review-required"
                audit_id = audit["id"]
                if save_changed_audits:
                    save_audit(home, audit)
            sources.append(
                {
                    "path": str(observed_path),
                    "display_path": display_path,
                    "status": status,
                    "applied_sha256": batch["source_sha256"],
                    "observed_sha256": observed_sha,
                    "stale_targets": stale_targets,
                    "candidate_count": int(candidate_count),
                    "audit_id": audit_id,
                    "checked_at": utc_now(),
                }
            )
        except (OSError, UnicodeError, ValueError):
            sources.append(
                {
                    "path": str(canonical),
                    "display_path": display_path,
                    "status": "unavailable",
                    "applied_sha256": batch["source_sha256"],
                    "observed_sha256": None,
                    "stale_targets": target_map(source_rows),
                    "candidate_count": 0,
                    "audit_id": None,
                    "checked_at": utc_now(),
                }
            )

    aggregate = {"semantic": [], "episodic": [], "rule": [], "state": []}
    for source in sources:
        for memory_type, identifiers in source["stale_targets"].items():
            aggregate[memory_type].extend(identifiers)
    aggregate = {
        key: list(dict.fromkeys(values)) for key, values in aggregate.items()
    }
    return {
        "schema_version": 1,
        "entity_id": entity_id,
        "entity_name": record_entity["name"],
        "project_root": str(project_root),
        "source_count": len(sources),
        "attention_count": sum(
            source["status"] in {
                "review-required", "unavailable", "source-limit-exceeded"
            }
            for source in sources
        ),
        "stale_targets": aggregate,
        "sources": sources,
        "checked_at": utc_now(),
    }


def _artifact_path(home: Path, kind: str, reference: str) -> Path:
    directory = (_workflow_root(home) / kind).resolve()
    candidate = Path(reference).expanduser()
    if candidate.suffix == ".json" or candidate.parent != Path("."):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(directory):
            raise ValueError(f"{kind[:-1]} file must be under {directory}")
        return resolved
    return directory / f"{reference}.json"


def load_artifact(home: Path, kind: str, reference: str) -> dict:
    path = _artifact_path(home, kind, reference)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"unknown {kind[:-1]}: {reference}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != WORKFLOW_SCHEMA:
        raise ValueError(f"unsupported {kind[:-1]} schema")
    return value


def _logical_rows(store: MemoryStore, conn) -> dict:
    tables = (
        "knowledge", "rules", "numerical_state", "entity_state", "entities",
        "relations", "memory_entities", "imported_events", "lifecycle",
        "knowledge_supersessions",
    )
    values: dict[str, list[dict]] = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        records = [dict(row) for row in rows]
        records.sort(key=_canonical_json)
        values[table] = records
    values["native_events_sha256"] = _digest(
        store.events_path.read_bytes() if store.events_path.exists() else b""
    )
    return values


def store_revision(store: MemoryStore) -> str:
    with store.connect() as conn:
        return _digest(_logical_rows(store, conn))


def _parse_assignments(values: Iterable[str], option: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"{option} expects ITEM=VALUE")
        item_id, value = raw.split("=", 1)
        if not item_id or not value:
            raise ValueError(f"{option} expects ITEM=VALUE")
        if item_id in output:
            raise ValueError(f"duplicate decision for {item_id}")
        output[item_id] = value
    return output


def build_review(
    audit: dict,
    store: MemoryStore,
    *,
    approve_ready: bool = False,
    assignments: Iterable[str] = (),
    rules: Iterable[str] = (),
    supersedes: Iterable[str] = (),
    rule_effect: str = "warn",
) -> dict:
    validate_audit(audit)
    if rule_effect not in {"warn", "block"}:
        raise ValueError("rule effect must be warn or block")
    by_id = {entry["id"]: entry for entry in audit["entries"]}
    decisions: dict[str, dict] = {}
    if approve_ready:
        duplicate_ids = {
            finding["duplicate"]
            for finding in audit["findings"]
            if finding.get("kind") == "exact_duplicate_candidate"
        }
        for entry in audit["entries"]:
            if entry["id"] in duplicate_ids:
                decisions[entry["id"]] = {"action": "skip", "reason": "exact-duplicate-candidate"}
            elif entry["status"] == "ready":
                decisions[entry["id"]] = {"action": entry["suggested_type"], "reason": "approved-ready"}

    explicit_seen: set[str] = set()
    for item_id, action in _parse_assignments(assignments, "--set").items():
        explicit_seen.add(item_id)
        if item_id not in by_id:
            raise ValueError(f"unknown audit item: {item_id}")
        if action not in {"semantic", "episodic", "state", "skip"}:
            raise ValueError("--set action must be semantic, episodic, state, or skip")
        if action == "state" and not by_id[item_id].get("structured"):
            raise ValueError(f"state decision requires an explicit key/value entry: {item_id}")
        decisions[item_id] = {"action": action, "reason": "explicit-review"}

    for item_id, pattern in _parse_assignments(rules, "--rule").items():
        if item_id in explicit_seen:
            raise ValueError(f"duplicate explicit decision for {item_id}")
        explicit_seen.add(item_id)
        if item_id not in by_id:
            raise ValueError(f"unknown audit item: {item_id}")
        try:
            compile_safe_rule_pattern(pattern)
            validate_rule_reason(by_id[item_id]["text"])
        except ValueError as exc:
            raise ValueError(f"invalid procedural rule for {item_id}: {exc}") from exc
        decisions[item_id] = {
            "action": "rule",
            "pattern": pattern,
            "effect": rule_effect,
            "reason": "explicit-rule-review",
        }

    for item_id, old_id in _parse_assignments(supersedes, "--supersede").items():
        if item_id in explicit_seen:
            raise ValueError(f"duplicate explicit decision for {item_id}")
        explicit_seen.add(item_id)
        if item_id not in by_id:
            raise ValueError(f"unknown audit item: {item_id}")
        with store.connect() as conn:
            existing_row = conn.execute(
                """SELECT k.id, k.status, k.global_scope,
                    EXISTS (
                        SELECT 1 FROM memory_entities me
                        JOIN entities e ON e.id = me.entity_id
                        WHERE me.target_type = 'semantic'
                          AND me.target_id = k.id
                          AND lower(e.name) = lower(?) AND e.type = ?
                    ) AS linked_to_entity
                FROM knowledge k WHERE k.id = ?""",
                (
                    audit["entity"]["name"],
                    audit["entity"]["type"],
                    old_id,
                ),
            ).fetchone()
        existing = dict(existing_row) if existing_row else None
        if not existing or existing["status"] != "active":
            raise ValueError(f"supersession target is not active: {old_id}")
        if existing["global_scope"] or not existing["linked_to_entity"]:
            raise ValueError(
                f"supersession target is not scoped to {audit['entity']['name']}: {old_id}"
            )
        decisions[item_id] = {
            "action": "supersede",
            "old_id": old_id,
            "reason": "explicit-supersession-review",
        }

    ordered = {item_id: decisions[item_id] for item_id in sorted(decisions)}
    revision = store_revision(store)
    identity = {
        "audit_id": audit["id"],
        "entity": audit["entity"],
        "source_sha256": audit["source"]["sha256"],
        "store_revision": revision,
        "decisions": ordered,
    }
    return {
        "schema_version": WORKFLOW_SCHEMA,
        "kind": "markdown-memory-review",
        "id": _stable_id("review", identity),
        "audit_id": audit["id"],
        "created_at": utc_now(),
        "entity": audit["entity"],
        "source": audit["source"],
        "store_revision": revision,
        "decisions": ordered,
        "counts": {
            "approved": sum(value["action"] != "skip" for value in ordered.values()),
            "skipped": sum(value["action"] == "skip" for value in ordered.values()),
            "unresolved": len(audit["entries"]) - len(ordered),
        },
        "claims": {
            "source_changed": False,
            "memory_records_changed": False,
            "rules_require_explicit_pattern": True,
            "state_requires_explicit_key_value": True,
        },
    }


def save_review(home: Path, review: dict) -> Path:
    _protect_runtime_home(home)
    path = _workflow_root(home) / "reviews" / f"{review['id']}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        comparable = (
            "schema_version", "kind", "id", "audit_id", "entity", "source",
            "store_revision", "decisions", "counts", "claims",
        )
        if all(existing.get(key) == review.get(key) for key in comparable):
            return path
    return _save_json(path, review)


def validate_audit(audit: dict, *, verify_source: bool = True) -> None:
    required = {
        "schema_version", "parser_version", "kind", "id", "entity", "source",
        "counts", "entries", "findings",
    }
    if not required <= set(audit) or audit.get("kind") != "markdown-memory-audit":
        raise ValueError("invalid audit plan")
    if audit.get("schema_version") != WORKFLOW_SCHEMA:
        raise ValueError("unsupported audit schema")
    if audit.get("parser_version") != PARSER_VERSION:
        raise ValueError("audit parser version is no longer supported; re-audit")
    identity = {
        "schema_version": audit["schema_version"],
        "parser_version": audit["parser_version"],
        "entity": audit["entity"],
        "source": audit["source"],
        "counts": audit["counts"],
        "entries": audit["entries"],
        "findings": audit["findings"],
    }
    if audit["id"] != _stable_id("audit", identity):
        raise ValueError("audit plan integrity check failed")
    if not verify_source:
        return
    try:
        rebuilt = build_audit(
            audit["source"]["path"],
            entity=audit["entity"]["name"],
        )
    except (OSError, ValueError) as exc:
        raise WorkflowConflict("source_changed: run brain-ai audit again") from exc
    comparable = ("schema_version", "parser_version", "kind", "id", "entity", "source", "counts", "entries", "findings")
    if any(rebuilt[key] != audit[key] for key in comparable):
        if rebuilt["source"] != audit["source"]:
            raise WorkflowConflict("source_changed: run brain-ai audit again")
        raise ValueError("audit plan integrity check failed")


def validate_review(review: dict) -> None:
    required = {
        "schema_version", "kind", "id", "audit_id", "entity", "source",
        "store_revision", "decisions",
    }
    if (
        not required <= set(review)
        or review.get("schema_version") != WORKFLOW_SCHEMA
        or review.get("kind") != "markdown-memory-review"
    ):
        raise ValueError("invalid review plan")
    if not isinstance(review["decisions"], dict):
        raise ValueError("review decisions must be an object")
    for item_id, decision in review["decisions"].items():
        if not isinstance(item_id, str) or not isinstance(decision, dict):
            raise ValueError("invalid review decision")
        if decision.get("action") not in ALLOWED_DECISIONS:
            raise ValueError(f"unknown reviewed action: {decision.get('action')}")
    identity = {
        "audit_id": review["audit_id"],
        "entity": review["entity"],
        "source_sha256": review["source"]["sha256"],
        "store_revision": review["store_revision"],
        "decisions": {key: review["decisions"][key] for key in sorted(review["decisions"])},
    }
    if review["id"] != _stable_id("review", identity):
        raise ValueError("review plan integrity check failed")


def resolve_review(home: Path, reference: str) -> dict:
    try:
        return load_artifact(home, "reviews", reference)
    except ValueError as direct_error:
        try:
            audit = load_artifact(home, "audits", reference)
        except ValueError:
            raise direct_error
        directory = _workflow_root(home) / "reviews"
        matches = []
        if directory.is_dir():
            for path in directory.glob("review_*.json"):
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("audit_id") == audit["id"]:
                    matches.append(value)
        if not matches:
            raise ValueError(f"audit has no saved review: {reference}")
        matches.sort(key=lambda value: value.get("created_at", ""))
        return matches[-1]


@contextlib.contextmanager
def _workflow_lock(home: Path, key: str) -> Iterator[None]:
    directory = _workflow_root(home) / "locks"
    _private_directory(directory)
    path = directory / f"{_digest(key)[:20]}.lock"
    with open_private_lock(path) as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            import fcntl
        except ImportError:  # pragma: no cover - Windows fallback
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ensure_entity(conn, name: str, entity_type: str) -> tuple[str, bool]:
    row = conn.execute(
        "SELECT id FROM entities WHERE lower(name) = lower(?) AND type = ?",
        (name, entity_type),
    ).fetchone()
    if row:
        return row["id"], False
    entity_id = new_id("ent")
    now = utc_now()
    conn.execute(
        """INSERT INTO entities
        (id, name, type, aliases_json, metadata_json, created_at, updated_at)
        VALUES (?, ?, ?, '[]', '{}', ?, ?)""",
        (entity_id, name, entity_type, now, now),
    )
    return entity_id, True


def _link_entity(conn, target_type: str, target_id: str, entity_id: str, now: str) -> bool:
    before = conn.total_changes
    conn.execute(
        """INSERT OR IGNORE INTO memory_entities
        (target_type, target_id, entity_id, role, created_at)
        VALUES (?, ?, ?, 'about', ?)""",
        (target_type, target_id, entity_id, now),
    )
    return conn.total_changes > before


def _parse_literal(value: str):
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _source_label(review: dict, entry: dict) -> str:
    source = review["source"]
    return (
        f"{source['path']}#L{entry['line_start']}-L{entry['line_end']}"
        f"@{source['sha256'][:12]}"
    )


def _decision_digest(decision: dict) -> str:
    identity = {"action": decision.get("action")}
    if decision.get("action") == "rule":
        identity.update(
            {"pattern": decision.get("pattern"), "effect": decision.get("effect")}
        )
    elif decision.get("action") == "supersede":
        identity["old_id"] = decision.get("old_id")
    return _digest(identity)


def _prior_import_is_current(
    conn,
    prior,
    *,
    action: str,
    entity_id: str,
    entry: dict,
) -> bool:
    target_id = prior["target_id"]
    payload = json.loads(prior["payload_json"])
    if action in {"semantic", "supersede"}:
        target = conn.execute(
            "SELECT status, global_scope FROM knowledge WHERE id = ?", (target_id,)
        ).fetchone()
        if not target or target["status"] != "active":
            return False
        linked = conn.execute(
            """SELECT 1 FROM memory_entities WHERE target_type = 'semantic'
            AND target_id = ? AND entity_id = ?""",
            (target_id, entity_id),
        ).fetchone()
        if not target["global_scope"] and not linked:
            return False
        old_id = payload.get("old_id")
        if old_id:
            old_link = conn.execute(
                """SELECT 1 FROM memory_entities WHERE target_type = 'semantic'
                AND target_id = ? AND entity_id = ?""",
                (old_id, entity_id),
            ).fetchone()
            if old_link:
                return False
            edge = conn.execute(
                """SELECT 1 FROM knowledge_supersessions
                WHERE old_id = ? AND replacement_id = ? AND entity_id = ?
                  AND status = 'active'""",
                (old_id, target_id, entity_id),
            ).fetchone()
            if not edge:
                return False
        return True
    if action == "episodic":
        target = conn.execute(
            """SELECT status, entity_ids_json FROM imported_events WHERE id = ?""",
            (target_id,),
        ).fetchone()
        if (
            not target
            or target["status"] != "active"
            or entity_id not in json.loads(target["entity_ids_json"])
        ):
            return False
        lifecycle = conn.execute(
            """SELECT operation FROM lifecycle
            WHERE target_type = 'episodic' AND target_id = ?
            ORDER BY created_at DESC LIMIT 1""",
            (target_id,),
        ).fetchone()
        return not lifecycle or lifecycle["operation"] not in {
            "archive",
            "delete",
            "migrate-to-knowledge-base",
            "migrate-to-rules",
        }
    if action == "rule":
        target = conn.execute(
            "SELECT enabled FROM rules WHERE id = ?", (target_id,)
        ).fetchone()
        linked = conn.execute(
            """SELECT 1 FROM memory_entities WHERE target_type = 'rule'
            AND target_id = ? AND entity_id = ?""",
            (target_id, entity_id),
        ).fetchone()
        return bool(target and target["enabled"] and linked)
    if action == "state":
        target = conn.execute(
            """SELECT value_json, source FROM entity_state
            WHERE entity_id = ? AND key = ?""",
            (entity_id, target_id),
        ).fetchone()
        structured = entry.get("structured")
        expected = json.dumps(
            _parse_literal(structured["value"]), ensure_ascii=False
        ) if structured else None
        return bool(
            target
            and target["value_json"] == expected
            and target["source"] == payload.get("source_label")
        )
    return False


def apply_review(home: Path, store: MemoryStore, review: dict, audit: dict) -> dict:
    validate_review(review)
    validate_audit(audit, verify_source=False)
    if (
        review.get("audit_id") != audit.get("id")
        or review.get("source") != audit.get("source")
        or review.get("entity") != audit.get("entity")
    ):
        raise ValueError("review does not match its audit")
    entries = {entry["id"]: entry for entry in audit["entries"]}
    approved = [value for value in review["decisions"].values() if value["action"] != "skip"]
    if not approved:
        raise ValueError("review has no approved imports")
    with _workflow_lock(home, review["source"]["path"]):
        with store.connect() as conn:
            existing_batch = conn.execute(
                """SELECT * FROM import_batches
                WHERE review_id = ? AND status IN ('applying', 'applied')
                ORDER BY created_at DESC LIMIT 1""",
                (review["id"],),
            ).fetchone()
            if existing_batch:
                batch = dict(existing_batch)
                if batch["status"] == "applied":
                    try:
                        current_source, current_raw, _ = _read_markdown(
                            review["source"]["path"]
                        )
                        source_file_changed = (
                            str(current_source) != review["source"]["path"]
                            or _digest(current_raw) != review["source"]["sha256"]
                        )
                    except (OSError, ValueError):
                        source_file_changed = True
                    entity_row = conn.execute(
                        "SELECT id, name, type FROM entities WHERE id = ?",
                        (batch["entity_id"],),
                    ).fetchone()
                    recovered = {
                        "schema_version": WORKFLOW_SCHEMA,
                        "kind": "markdown-memory-apply-receipt",
                        "id": batch["id"],
                        "status": "already_applied",
                        "review_id": review["id"],
                        "audit_id": batch["audit_id"],
                        "entity": dict(entity_row) if entity_row else review["entity"],
                        "source": review["source"],
                        "before_revision": batch["before_revision"],
                        "results": json.loads(batch["result_json"]),
                        "after_revision": batch["after_revision"],
                        "source_file_changed": source_file_changed,
                        "physical_erasure": False,
                        "created_at": batch["created_at"],
                    }
                    receipt_path = (
                        _workflow_root(home)
                        / "receipts"
                        / f"{batch['id']}.json"
                    )
                    if not receipt_path.exists():
                        _save_json(receipt_path, {**recovered, "status": "applied"})
                    return recovered
                raise WorkflowConflict(f"review batch is {batch['status']}; create a new audit")

            # Revalidate an unapplied serialized review independently of
            # build_review and before any mutation.  Already-applied immutable
            # reviews return their receipt above, even if a newer release has
            # tightened rule admission since the original application.
            for item_id, decision in review["decisions"].items():
                if decision.get("action") != "rule":
                    continue
                entry = entries.get(item_id)
                pattern = decision.get("pattern")
                effect = decision.get("effect")
                if not entry or not pattern or effect not in {"warn", "block"}:
                    raise ValueError(
                        f"rule import requires an explicit item, pattern, and effect: {item_id}"
                    )
                try:
                    compile_safe_rule_pattern(pattern)
                    validate_rule_reason(entry["text"])
                except ValueError as exc:
                    raise ValueError(
                        f"invalid procedural rule for {item_id}: {exc}"
                    ) from exc

            validate_audit(audit)
            source, raw, _ = _read_markdown(review["source"]["path"])
            if (
                str(source) != review["source"]["path"]
                or _digest(raw) != review["source"]["sha256"]
            ):
                raise WorkflowConflict("source_changed: run brain-ai audit again")
            conn.execute("BEGIN IMMEDIATE")
            current_revision = _digest(_logical_rows(store, conn))
            if current_revision != review["store_revision"]:
                conn.rollback()
                raise WorkflowConflict("store_changed: review the audit again before applying")

            now = utc_now()
            batch_id = new_id("batch")
            entity_id, entity_created = _ensure_entity(
                conn, review["entity"]["name"], review["entity"]["type"]
            )
            conn.execute(
                """INSERT INTO import_batches
                (id, review_id, audit_id, entity_id, source_path, source_sha256,
                 before_revision, after_revision, status, result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'applying', '[]', ?)""",
                (
                    batch_id,
                    review["id"],
                    audit["id"],
                    entity_id,
                    review["source"]["path"],
                    review["source"]["sha256"],
                    current_revision,
                    now,
                ),
            )
            results: list[dict] = []
            seen_state_keys: set[str] = set()
            try:
                for item_id, decision in sorted(review["decisions"].items()):
                    action = decision.get("action")
                    if action not in ALLOWED_DECISIONS:
                        raise ValueError(f"unknown reviewed action: {action}")
                    entry = entries.get(item_id)
                    if not entry:
                        raise ValueError(f"review references unknown audit item: {item_id}")
                    if action == "skip":
                        results.append({"item_id": item_id, "status": "skipped", "memory_type": None})
                        continue
                    entry_fingerprint = entry["fingerprint"]
                    decision_digest = _decision_digest(decision)
                    prior_import = conn.execute(
                        """SELECT id, batch_id, status, target_id, payload_json
                        FROM import_ledger
                        WHERE entry_fingerprint = ? AND entity_id = ?
                          AND decision_digest IN (?, ?) AND status = 'active'""",
                        (
                            entry_fingerprint,
                            entity_id,
                            decision_digest,
                            f"legacy:{action}",
                        ),
                    ).fetchone()
                    if prior_import:
                        if not _prior_import_is_current(
                            conn,
                            prior_import,
                            action=action,
                            entity_id=entity_id,
                            entry=entry,
                        ):
                            raise WorkflowConflict(
                                "prior_import_changed: review lifecycle or current state "
                                f"explicitly before re-importing {item_id}"
                            )
                        if prior_import["batch_id"] != batch_id:
                            conn.execute(
                                """INSERT OR IGNORE INTO import_dependencies
                                (id, dependent_batch_id, provider_ledger_id, created_at)
                                VALUES (?, ?, ?, ?)""",
                                (
                                    new_id("dep"),
                                    batch_id,
                                    prior_import["id"],
                                    now,
                                ),
                            )
                        results.append(
                            {
                                "item_id": item_id,
                                "status": "already_imported",
                                "memory_type": action,
                                "target_id": prior_import["target_id"],
                                "depends_on_batch": prior_import["batch_id"],
                            }
                        )
                        continue

                    source_label = _source_label(review, entry)
                    payload: dict = {"decision": decision, "entity_created": entity_created}
                    target_id: str | None = None
                    created_target = False
                    link_created = False

                    if action in {"semantic", "supersede"}:
                        clean = entry["text"].strip()
                        content_hash = _digest(clean)
                        existing = conn.execute(
                            """SELECT id, status, global_scope, supersedes FROM knowledge
                            WHERE content_hash = ?""",
                            (content_hash,),
                        ).fetchone()
                        old_id = decision.get("old_id") if action == "supersede" else None
                        old = None
                        old_links: list[dict] = []
                        if old_id:
                            old = conn.execute(
                                """SELECT id, status, global_scope FROM knowledge
                                WHERE id = ?""",
                                (old_id,),
                            ).fetchone()
                            if not old or old["status"] != "active":
                                raise WorkflowConflict(
                                    f"supersession target changed: {old_id}"
                                )
                            if old["global_scope"]:
                                raise WorkflowConflict(
                                    "project-scoped supersession cannot replace global memory"
                                )
                            old_links = [
                                dict(row)
                                for row in conn.execute(
                                    """SELECT * FROM memory_entities
                                    WHERE target_type = 'semantic' AND target_id = ?
                                      AND entity_id = ?""",
                                    (old_id, entity_id),
                                ).fetchall()
                            ]
                            if not old_links:
                                raise WorkflowConflict(
                                    "supersession target is not linked to the reviewed project"
                                )
                            if existing and existing["id"] == old_id:
                                raise ValueError(
                                    "replacement text is identical to the supersession target"
                                )
                        if existing:
                            target_id = existing["id"]
                            payload["existing_status"] = existing["status"]
                            if old_id:
                                payload["replacement_supersedes_before"] = existing["supersedes"]
                                conn.execute(
                                    """UPDATE knowledge
                                    SET supersedes = COALESCE(supersedes, ?), updated_at = ?
                                    WHERE id = ?""",
                                    (old_id, now, target_id),
                                )
                            if existing["status"] != "active":
                                link_count = conn.execute(
                                    """SELECT COUNT(*) FROM memory_entities
                                    WHERE target_type = 'semantic' AND target_id = ?""",
                                    (target_id,),
                                ).fetchone()[0]
                                if (
                                    existing["status"] != "archived"
                                    or existing["global_scope"]
                                    or link_count
                                ):
                                    raise WorkflowConflict(
                                        "identical semantic memory exists but is inactive; "
                                        "review its lifecycle explicitly"
                                    )
                                conn.execute(
                                    """UPDATE knowledge SET status = 'active', updated_at = ?
                                    WHERE id = ?""",
                                    (now, target_id),
                                )
                                payload["reactivated_target"] = True
                        else:
                            target_id = new_id("mem")
                            conn.execute(
                                """INSERT INTO knowledge
                                (id, text, source, tags_json, status, content_hash,
                                 global_scope, supersedes, created_at, updated_at)
                                VALUES (?, ?, ?, '[]', 'active', ?, 0, ?, ?, ?)""",
                                (
                                    target_id,
                                    clean,
                                    source_label,
                                    content_hash,
                                    old_id,
                                    now,
                                    now,
                                ),
                            )
                            created_target = True
                        if old_id:
                            payload["old_id"] = old_id
                            payload["old_status"] = old["status"]
                            payload["old_entity_links"] = old_links
                            conn.execute(
                                """DELETE FROM memory_entities
                                WHERE target_type = 'semantic' AND target_id = ?
                                  AND entity_id = ?""",
                                (old_id, entity_id),
                            )
                            remaining_links = conn.execute(
                                """SELECT COUNT(*) FROM memory_entities
                                WHERE target_type = 'semantic' AND target_id = ?""",
                                (old_id,),
                            ).fetchone()[0]
                            payload["old_status_changed"] = remaining_links == 0
                            if not remaining_links:
                                conn.execute(
                                    """UPDATE knowledge SET status = 'superseded',
                                    updated_at = ? WHERE id = ?""",
                                    (now, old_id),
                                )
                            edge = store._record_knowledge_supersession(
                                conn,
                                old_id=old_id,
                                replacement_id=target_id,
                                entity_id=entity_id,
                                source=source_label,
                                created_at=now,
                                batch_id=batch_id,
                            )
                            payload["supersession_edge_id"] = edge["id"]
                        link_created = bool(
                            (not existing or not existing["global_scope"])
                            and _link_entity(
                                conn, "semantic", target_id, entity_id, now
                            )
                        )

                    elif action == "episodic":
                        target_id = new_id("evt")
                        conn.execute(
                            """INSERT INTO imported_events
                            (id, text, source, tags_json, promote_to, rule_pattern,
                             entity_ids_json, status, created_at)
                            VALUES (?, ?, ?, '[]', NULL, NULL, ?, 'active', ?)""",
                            (target_id, entry["text"].strip(), source_label, json.dumps([entity_id]), now),
                        )
                        created_target = True

                    elif action == "state":
                        structured = entry.get("structured")
                        if not structured:
                            raise ValueError(f"state import lacks explicit key/value: {item_id}")
                        key = structured["key"]
                        if key in seen_state_keys:
                            raise ValueError(f"review contains more than one state value for key: {key}")
                        seen_state_keys.add(key)
                        previous = conn.execute(
                            "SELECT * FROM entity_state WHERE entity_id = ? AND key = ?",
                            (entity_id, key),
                        ).fetchone()
                        payload["previous_state"] = dict(previous) if previous else None
                        value = _parse_literal(structured["value"])
                        conn.execute(
                            """INSERT INTO entity_state
                            (entity_id, key, value_json, source, updated_at)
                            VALUES (?, ?, ?, ?, ?) ON CONFLICT(entity_id, key) DO UPDATE SET
                            value_json=excluded.value_json, source=excluded.source,
                            updated_at=excluded.updated_at""",
                            (entity_id, key, json.dumps(value, ensure_ascii=False), source_label, now),
                        )
                        target_id = key
                        created_target = previous is None

                    elif action == "rule":
                        pattern = decision.get("pattern")
                        effect = decision.get("effect")
                        target_id = new_id("rule")
                        conn.execute(
                            """INSERT INTO rules
                            (id, pattern, effect, reason, source, enabled, created_at)
                            VALUES (?, ?, ?, ?, ?, 1, ?)""",
                            (target_id, pattern, effect, entry["text"].strip(), source_label, now),
                        )
                        link_created = _link_entity(conn, "rule", target_id, entity_id, now)
                        created_target = True

                    payload.update(
                        {
                            "created_target": created_target,
                            "link_created": link_created,
                            "source_label": source_label,
                        }
                    )
                    conn.execute(
                        """INSERT INTO import_ledger
                        (id, entry_fingerprint, entity_id, decision_digest,
                         batch_id, source_path, source_sha256, fragment_sha256,
                         line_start, line_end, memory_type, target_id, status,
                         payload_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)""",
                        (
                            new_id("import"),
                            entry_fingerprint,
                            entity_id,
                            decision_digest,
                            batch_id,
                            review["source"]["path"],
                            review["source"]["sha256"],
                            entry["fragment_sha256"],
                            entry["line_start"],
                            entry["line_end"],
                            action,
                            target_id,
                            _canonical_json(payload),
                            now,
                        ),
                    )
                    results.append(
                        {
                            "item_id": item_id,
                            "status": "imported" if created_target else "already_present",
                            "memory_type": "semantic" if action == "supersede" else action,
                            "target_id": target_id,
                            "source": source_label,
                        }
                    )

                try:
                    final_source, final_raw, _ = _read_markdown(review["source"]["path"])
                except ValueError as exc:
                    raise WorkflowConflict(
                        "source_changed_during_apply: re-audit before applying"
                    ) from exc
                if (
                    str(final_source) != review["source"]["path"]
                    or _digest(final_raw) != review["source"]["sha256"]
                ):
                    raise WorkflowConflict("source_changed_during_apply: re-audit before applying")
                after_revision = _digest(_logical_rows(store, conn))
                conn.execute(
                    """UPDATE import_batches SET after_revision = ?, status = 'applied',
                    result_json = ? WHERE id = ?""",
                    (after_revision, _canonical_json(results), batch_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    receipt = {
        "schema_version": WORKFLOW_SCHEMA,
        "kind": "markdown-memory-apply-receipt",
        "id": batch_id,
        "status": "applied",
        "review_id": review["id"],
        "audit_id": audit["id"],
        "entity": {**review["entity"], "id": entity_id},
        "source": review["source"],
        "before_revision": review["store_revision"],
        "after_revision": after_revision,
        "results": results,
        "source_file_changed": False,
        "physical_erasure": False,
        "created_at": utc_now(),
    }
    _save_json(_workflow_root(home) / "receipts" / f"{batch_id}.json", receipt)
    store.append_audit({"event": "markdown_memory_apply", **receipt})
    # A successful apply establishes a new current projection. Remove any
    # cached drift verdict immediately; the next loop event will repopulate a
    # complete source snapshot from the new batch.
    with store.connect() as conn:
        conn.execute(
            """DELETE FROM loop_source_freshness
            WHERE entity_id=? AND source_path=?""",
            (entity_id, review["source"]["path"]),
        )
    return receipt


def rollback_batch(home: Path, store: MemoryStore, reference: str) -> dict:
    with _workflow_lock(home, reference):
        with store.connect() as conn:
            row = conn.execute(
                """SELECT * FROM import_batches WHERE id = ? OR review_id = ?
                ORDER BY CASE WHEN id = ? THEN 0
                              WHEN status = 'applied' THEN 1
                              WHEN status = 'applying' THEN 2
                              ELSE 3 END,
                         created_at DESC
                LIMIT 1""",
                (reference, reference, reference),
            ).fetchone()
            if not row:
                raise ValueError(f"unknown import batch: {reference}")
            batch = dict(row)
            if batch["status"] == "rolled_back":
                return {
                    "id": batch["id"],
                    "status": "already_rolled_back",
                    "physical_erasure": False,
                }
            if batch["status"] != "applied":
                raise WorkflowConflict(f"batch cannot be rolled back from status {batch['status']}")
            conn.execute("BEGIN IMMEDIATE")
            dependent = conn.execute(
                """SELECT d.dependent_batch_id FROM import_dependencies d
                JOIN import_ledger l ON l.id = d.provider_ledger_id
                JOIN import_batches b ON b.id = d.dependent_batch_id
                WHERE l.batch_id = ? AND b.status = 'applied'
                LIMIT 1""",
                (batch["id"],),
            ).fetchone()
            if dependent:
                conn.rollback()
                raise WorkflowConflict(
                    "batch_has_active_dependents: roll back dependent batch "
                    f"{dependent['dependent_batch_id']} first"
                )
            ledger = conn.execute(
                """SELECT * FROM import_ledger
                WHERE batch_id = ?
                ORDER BY created_at DESC, rowid DESC""",
                (batch["id"],),
            ).fetchall()
            for raw in ledger:
                item = dict(raw)
                if item["memory_type"] not in {"semantic", "supersede"}:
                    continue
                payload = json.loads(item["payload_json"])
                affects_target = bool(
                    payload.get("created_target")
                    or payload.get("reactivated_target")
                )
                affects_scope = bool(payload.get("link_created"))
                if not affects_target and not affects_scope:
                    continue
                dependent = conn.execute(
                    """SELECT other.batch_id FROM import_ledger other
                    JOIN import_batches b ON b.id = other.batch_id
                    WHERE other.target_id = ? AND other.batch_id != ?
                      AND other.status = 'active' AND b.status = 'applied'
                      AND other.memory_type IN ('semantic', 'supersede')
                      AND (? = 1 OR other.entity_id = ?)
                    LIMIT 1""",
                    (
                        item["target_id"],
                        batch["id"],
                        int(affects_target),
                        batch["entity_id"],
                    ),
                ).fetchone()
                if dependent:
                    conn.rollback()
                    raise WorkflowConflict(
                        "batch_has_active_dependents: roll back dependent batch "
                        f"{dependent['batch_id']} first"
                    )
            current_revision = _digest(_logical_rows(store, conn))
            if current_revision != batch["after_revision"]:
                conn.rollback()
                raise WorkflowConflict("store_changed: rollback would overwrite later memory changes")
            now = utc_now()
            for raw in ledger:
                item = dict(raw)
                payload = json.loads(item["payload_json"])
                memory_type = item["memory_type"]
                target_id = item["target_id"]
                if memory_type in {"semantic", "supersede"}:
                    if payload.get("link_created"):
                        conn.execute(
                            """DELETE FROM memory_entities
                            WHERE target_type = 'semantic' AND target_id = ?
                              AND entity_id = ? AND role = 'about'""",
                            (target_id, batch["entity_id"]),
                        )
                    if payload.get("created_target"):
                        conn.execute(
                            "UPDATE knowledge SET status = 'archived', updated_at = ? WHERE id = ?",
                            (now, target_id),
                        )
                    elif payload.get("reactivated_target"):
                        conn.execute(
                            "UPDATE knowledge SET status = ?, updated_at = ? WHERE id = ?",
                            (payload.get("existing_status", "archived"), now, target_id),
                        )
                    if payload.get("old_id"):
                        edge_id = payload.get("supersession_edge_id")
                        if edge_id:
                            conn.execute(
                                """UPDATE knowledge_supersessions
                                SET status = 'rolled_back', rolled_back_at = ?
                                WHERE id = ? AND status = 'active'""",
                                (now, edge_id),
                            )
                        if "replacement_supersedes_before" in payload:
                            conn.execute(
                                "UPDATE knowledge SET supersedes = ? WHERE id = ?",
                                (payload["replacement_supersedes_before"], target_id),
                            )
                        if payload.get("old_status_changed"):
                            conn.execute(
                                "UPDATE knowledge SET status = ?, updated_at = ? WHERE id = ?",
                                (
                                    payload.get("old_status", "active"),
                                    now,
                                    payload["old_id"],
                                ),
                            )
                        for old_link in payload.get("old_entity_links", []):
                            conn.execute(
                                """INSERT OR IGNORE INTO memory_entities
                                (target_type, target_id, entity_id, role, created_at)
                                VALUES (?, ?, ?, ?, ?)""",
                                (
                                    old_link["target_type"],
                                    old_link["target_id"],
                                    old_link["entity_id"],
                                    old_link["role"],
                                    old_link["created_at"],
                                ),
                            )
                elif memory_type == "episodic":
                    conn.execute(
                        "UPDATE imported_events SET status = 'rolled_back' WHERE id = ?", (target_id,)
                    )
                elif memory_type == "rule":
                    conn.execute("UPDATE rules SET enabled = 0 WHERE id = ?", (target_id,))
                elif memory_type == "state":
                    previous = payload.get("previous_state")
                    if previous:
                        conn.execute(
                            """UPDATE entity_state SET value_json = ?, source = ?, updated_at = ?
                            WHERE entity_id = ? AND key = ?""",
                            (
                                previous["value_json"],
                                previous["source"],
                                previous["updated_at"],
                                batch["entity_id"],
                                target_id,
                            ),
                        )
                    else:
                        conn.execute(
                            "DELETE FROM entity_state WHERE entity_id = ? AND key = ?",
                            (batch["entity_id"], target_id),
                        )
                conn.execute(
                    "UPDATE import_ledger SET status = 'rolled_back' WHERE id = ?",
                    (item["id"],),
                )
            conn.execute(
                "UPDATE import_batches SET status = 'rolled_back', rolled_back_at = ? WHERE id = ?",
                (now, batch["id"]),
            )
            rolled_back_revision = _digest(_logical_rows(store, conn))
            conn.commit()
    result = {
        "id": batch["id"],
        "status": "rolled_back",
        "rolled_back_revision": rolled_back_revision,
        "physical_erasure": False,
        "evidence_retained": True,
        "created_at": utc_now(),
    }
    store.append_audit({"event": "markdown_memory_rollback", **result})
    return result


MANAGED_ENV = {"BRAIN_AI_MEMORY_MANAGED": "1"}
CODEX_BEGIN = "# BEGIN brain-ai-memory managed MCP\n"
CODEX_END = "# END brain-ai-memory managed MCP\n"


def _managed_mcp_args(value) -> dict | None:
    if not isinstance(value, list) or len(value) != 6:
        return None
    if value[:2] != ["-m", "brain_ai_memory.mcp_server"]:
        return None
    if value[2] != "--home" or value[4] not in {"--entity", "--locked-entity"}:
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    if not value[3] or not value[5]:
        return None
    return {
        "home": value[3],
        "entity": value[5],
        "entity_locked": value[4] == "--locked-entity",
    }


def _managed_python_command(value) -> bool:
    if not isinstance(value, str) or not Path(value).is_absolute():
        return False
    return re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", Path(value).name.lower()) is not None


def entity_references_match(home: Path, left: str, right: str) -> bool:
    """Compare two entity references by stable identity when possible."""
    left_value = left.strip()
    right_value = right.strip()
    if not left_value or not right_value:
        return left_value == right_value
    if left_value.casefold() == right_value.casefold():
        return True
    store = MemoryStore(Path(home).expanduser().resolve())
    if not store.db_path.is_file():
        return False
    try:
        return store.get_entity(left_value)["id"] == store.get_entity(right_value)["id"]
    except (KeyError, ValueError, OSError, sqlite3.Error):
        return False


def _managed_json_server(value) -> bool:
    if not isinstance(value, dict) or not set(value).issubset({"command", "args", "env"}):
        return False
    command = value.get("command")
    environment = value.get("env", {})
    return (
        _managed_python_command(command)
        and _managed_mcp_args(value.get("args")) is not None
        and environment == MANAGED_ENV
    )


def _managed_toml_server(value) -> bool:
    """Recognize only the exact table shape emitted inside our marked block."""
    return (
        isinstance(value, dict)
        and set(value) == {"command", "args"}
        and _managed_python_command(value.get("command"))
        and _managed_mcp_args(value.get("args")) is not None
    )


def _load_json_config(text: str, path: Path) -> dict:
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"refusing to edit invalid JSON config: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"config root must be an object: {path}")
    return value


def _load_toml_config(text: str, path: Path) -> dict:
    if not text:
        return {}
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"refusing to edit invalid TOML config: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"config root must be a table: {path}")
    return value


def _server_entry(config: dict) -> dict | None:
    servers = config.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object")
    value = servers.get("brain-ai-memory")
    return value if isinstance(value, dict) else value


def _codex_entry(config: dict) -> dict | None:
    servers = config.get("mcp_servers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcp_servers must be a table")
    value = servers.get("brain-ai-memory")
    return value if isinstance(value, dict) else value


def _managed_toml_entry(text: str, path: Path) -> dict | None:
    """Return a Codex entry only when the marked block owns all of it."""
    config = _load_toml_config(text, path)
    parsed_entry = _codex_entry(config)
    start = text.find(CODEX_BEGIN)
    finish = text.find(CODEX_END)
    if (start == -1) != (finish == -1) or (start != -1 and finish < start):
        raise ValueError("invalid brain-ai-memory managed block in Codex config")
    if text.count(CODEX_BEGIN) > 1 or text.count(CODEX_END) > 1:
        raise ValueError("multiple brain-ai-memory managed blocks in Codex config")
    if start == -1:
        if parsed_entry is not None:
            raise ValueError("brain-ai-memory already exists outside the managed block")
        return None

    block_finish = finish + len(CODEX_END)
    block_config = _load_toml_config(text[start:block_finish], path)
    block_entry = _codex_entry(block_config)
    expected_block = {"mcp_servers": {"brain-ai-memory": block_entry}}
    remaining_config = _load_toml_config(
        text[:start] + text[block_finish:], path
    )
    if (
        not _managed_toml_server(parsed_entry)
        or not _managed_toml_server(block_entry)
        or parsed_entry != block_entry
        or block_config != expected_block
        or _codex_entry(remaining_config) is not None
    ):
        raise ValueError(
            "managed brain-ai-memory table is missing, invalid, or has content "
            "outside the managed block"
        )
    return parsed_entry


def _json_config_change(
    path: Path,
    server: dict,
    *,
    disconnect: bool,
    before: str,
) -> tuple[str, str]:
    config = _load_json_config(before, path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be an object")
    existing = servers.get("brain-ai-memory")
    if existing is not None and not _managed_json_server(existing):
        raise ValueError("brain-ai-memory entry is not managed by this command")
    if disconnect:
        if existing is None:
            return before, before
        del servers["brain-ai-memory"]
        if not servers:
            config.pop("mcpServers", None)
    else:
        servers["brain-ai-memory"] = server
    after = json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return before, after


def _toml_config_change(
    path: Path,
    command: str,
    args: list[str],
    *,
    disconnect: bool,
    before: str,
) -> tuple[str, str]:
    _managed_toml_entry(before, path)
    start = before.find(CODEX_BEGIN)
    finish = before.find(CODEX_END)
    block = (
        CODEX_BEGIN
        + "[mcp_servers.brain-ai-memory]\n"
        + f"command = {json.dumps(command, ensure_ascii=False)}\n"
        + f"args = {_canonical_json(args)}\n"
        + CODEX_END
    )
    if start != -1:
        finish += len(CODEX_END)
        after = before[:start] + ("" if disconnect else block) + before[finish:]
    elif disconnect:
        after = before
    else:
        separator = "" if not before or before.endswith("\n\n") else ("\n" if before.endswith("\n") else "\n\n")
        after = before + separator + block
    after_entry = _managed_toml_entry(after, path)
    if disconnect and after_entry is not None:
        raise ValueError("brain-ai-memory content remains outside the managed block")
    if not disconnect and not _managed_toml_server(after_entry):
        raise ValueError("generated brain-ai-memory managed block is invalid")
    return before, after


def _redacted_managed_entry(value) -> dict:
    if not isinstance(value, dict):
        return {"status": "absent"}
    output = {
        "command": safe_display(str(value.get("command", ""))),
        "args": [safe_display(str(item)) for item in value.get("args", [])]
        if isinstance(value.get("args", []), list)
        else "<invalid>",
    }
    environment = value.get("env", {})
    if environment:
        output["env"] = MANAGED_ENV if environment == MANAGED_ENV else "<redacted>"
    return output


def _managed_config_diff(path: Path, before_entry, after_entry) -> str:
    before = _canonical_json(_redacted_managed_entry(before_entry)) + "\n"
    after = _canonical_json(_redacted_managed_entry(after_entry)) + "\n"
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"{path} (brain-ai-memory entry only)",
            tofile=f"{path} (brain-ai-memory entry only)",
        )
    )


def _validate_config_path(path: Path, config_root: Path) -> None:
    lexical = Path(os.path.abspath(path))
    resolved_parent = path.parent.resolve()
    if (
        path.is_symlink()
        or not lexical.is_relative_to(config_root)
        or not resolved_parent.is_relative_to(config_root)
    ):
        raise ValueError("refusing to read or edit a host config through a symbolic link")


@contextlib.contextmanager
def _pinned_config_parent(
    path: Path,
    config_root: Path,
    *,
    create: bool,
) -> Iterator[tuple[int | None, bool]]:
    """Pin the in-root config parent across read, compare, replace, and verify."""
    _validate_config_path(path, config_root)
    if not _relative_fd_io_available():  # pragma: no cover - non-POSIX fallback
        if create:
            path.parent.mkdir(parents=True, exist_ok=True)
        _validate_config_path(path, config_root)
        yield None, path.parent.is_dir()
        return

    try:
        relative_parent = Path(os.path.abspath(path.parent)).relative_to(config_root)
    except ValueError as exc:
        raise ValueError("host config is outside the selected config root") from exc
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = _open_directory_components(config_root, directory_flags)
    available = True
    try:
        for component in relative_parent.parts:
            try:
                next_descriptor = os.open(
                    component,
                    directory_flags,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    available = False
                    break
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                next_descriptor = os.open(
                    component,
                    directory_flags,
                    dir_fd=descriptor,
                )
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor if available else None, available
        if available:
            expected = os.fstat(descriptor)
            verification = _open_directory_components(
                config_root,
                directory_flags,
            )
            try:
                for component in relative_parent.parts:
                    next_verification = os.open(
                        component,
                        directory_flags,
                        dir_fd=verification,
                    )
                    os.close(verification)
                    verification = next_verification
                observed = os.fstat(verification)
            except OSError as exc:
                raise WorkflowConflict(
                    "config_changed: host config parent changed during update"
                ) from exc
            finally:
                os.close(verification)
            if (observed.st_dev, observed.st_ino) != (
                expected.st_dev,
                expected.st_ino,
            ):
                raise WorkflowConflict(
                    "config_changed: host config parent changed during update"
                )
    except OSError as exc:
        raise ValueError(
            "refusing to read or edit a host config through a symbolic link"
        ) from exc
    finally:
        os.close(descriptor)


def _read_config_at(
    path: Path,
    parent_descriptor: int | None,
    *,
    available: bool,
) -> tuple[str, int | None]:
    if not available:
        return "", None
    if parent_descriptor is None:  # pragma: no cover - non-POSIX fallback
        if not path.exists():
            return "", None
        if path.is_symlink() or not path.is_file():
            raise ValueError("host config must be a regular file, not a symbolic link")
        return path.read_text(encoding="utf-8"), stat.S_IMODE(path.stat().st_mode)

    try:
        initial = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return "", None
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise ValueError("host config must be a regular file, not a symbolic link")
    descriptor = os.open(
        path.name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_descriptor,
    )
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (initial.st_dev, initial.st_ino):
            raise WorkflowConflict("config_changed: inspect the host config again")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            text = handle.read()
            final_descriptor = os.fstat(handle.fileno())
        final_path = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        (final_descriptor.st_dev, final_descriptor.st_ino)
        != (initial.st_dev, initial.st_ino)
        or (final_path.st_dev, final_path.st_ino)
        != (initial.st_dev, initial.st_ino)
        or (final_descriptor.st_size, final_descriptor.st_mtime_ns)
        != (initial.st_size, initial.st_mtime_ns)
    ):
        raise WorkflowConflict("config_changed: inspect the host config again")
    return text, stat.S_IMODE(initial.st_mode)


def _read_pinned_config(path: Path, config_root: Path) -> tuple[str, int | None]:
    with _pinned_config_parent(path, config_root, create=False) as (
        parent_descriptor,
        available,
    ):
        return _read_config_at(
            path,
            parent_descriptor,
            available=available,
        )


def connection_change(
    home: Path,
    host: str,
    *,
    entity: str,
    scope: str = "project",
    project_root: str | Path = ".",
    disconnect: bool = False,
    apply: bool = False,
    _transaction_details: bool = False,
) -> dict:
    if host not in {"codex", "claude-code"}:
        raise ValueError("host must be codex or claude-code")
    if scope not in {"project", "user"}:
        raise ValueError("scope must be project or user")
    if not disconnect and not entity.strip():
        raise ValueError("--entity is required for a project-scoped default")
    root = Path(project_root).expanduser().resolve()
    if scope == "project" and not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")
    # Keep the interpreter path used to launch the CLI.  ``Path.resolve()``
    # dereferences a virtualenv's ``python`` symlink and can silently point the
    # host at the base interpreter where brain-ai-memory is not installed.
    command = os.path.abspath(sys.executable)
    entity_flag = "--locked-entity" if scope == "project" else "--entity"
    requested_entity = entity.strip()

    def managed_arguments(before_entry: dict | None) -> list[str]:
        effective_entity = requested_entity
        if isinstance(before_entry, dict):
            configured = _managed_mcp_args(before_entry.get("args"))
            if (
                configured
                and configured["home"] == str(home)
                and entity_references_match(
                    home, configured["entity"], requested_entity
                )
            ):
                effective_entity = configured["entity"]
        return [
            "-m",
            "brain_ai_memory.mcp_server",
            "--home",
            str(home),
            entity_flag,
            effective_entity,
        ]

    if host == "claude-code":
        path = root / ".mcp.json" if scope == "project" else Path.home() / ".claude.json"
        config_root = root if scope == "project" else Path.home().resolve()
        before, before_mode = _read_pinned_config(path, config_root)
        before_entry = _server_entry(_load_json_config(before, path))
        arguments = managed_arguments(
            before_entry if _managed_json_server(before_entry) else None
        )
        server = {"command": command, "args": arguments, "env": MANAGED_ENV}
        before, after = _json_config_change(
            path,
            server,
            disconnect=disconnect,
            before=before,
        )
        after_entry = _server_entry(_load_json_config(after, path))
    else:
        path = root / ".codex" / "config.toml" if scope == "project" else Path.home() / ".codex" / "config.toml"
        config_root = root if scope == "project" else Path.home().resolve()
        before, before_mode = _read_pinned_config(path, config_root)
        before_entry = _managed_toml_entry(before, path)
        arguments = managed_arguments(before_entry)
        before, after = _toml_config_change(
            path,
            command,
            arguments,
            disconnect=disconnect,
            before=before,
        )
        after_entry = _codex_entry(_load_toml_config(after, path))
    if disconnect and isinstance(before_entry, dict):
        configured = _managed_mcp_args(before_entry.get("args"))
        if not configured or configured["home"] != str(home):
            raise ValueError(
                "managed connection belongs to a different Brain-AI home"
            )
        if entity.strip() and not entity_references_match(
            home, configured["entity"], entity
        ):
            raise ValueError("managed connection belongs to a different entity")
    changed = before != after
    diff = CONTROL_RE.sub("", _managed_config_diff(path, before_entry, after_entry))
    if apply and changed:
        with _workflow_lock(home, f"host-config:{path}"):
            with _pinned_config_parent(path, config_root, create=True) as (
                parent_descriptor,
                available,
            ):
                try:
                    current, current_mode = _read_config_at(
                        path,
                        parent_descriptor,
                        available=available,
                    )
                except (OSError, UnicodeError, ValueError) as exc:
                    raise WorkflowConflict(
                        "config_changed: inspect the host config again"
                    ) from exc
                if current != before:
                    raise WorkflowConflict(
                        "config_changed: preview the host config again"
                    )
                if before:
                    backup = (
                        _workflow_root(home)
                        / "config-backups"
                        / f"{host}-{_digest(before)[:12]}.bak"
                    )
                    if not backup.exists():
                        _atomic_bytes(backup, before.encode("utf-8"))
                _atomic_bytes_at(
                    path,
                    after.encode("utf-8"),
                    mode=current_mode or 0o644,
                    parent_descriptor=parent_descriptor,
                )
                verified, _ = _read_config_at(
                    path,
                    parent_descriptor,
                    available=available,
                )
                if verified != after:
                    raise WorkflowConflict(
                        "config_changed: host config verification failed"
                    )
    next_command = None
    if not apply and changed:
        parts = [
            "brain-ai",
            "--home",
            shlex.quote(str(home)),
            "disconnect" if disconnect else "connect",
            host,
        ]
        if entity.strip():
            parts.extend(["--entity", shlex.quote(entity.strip())])
        parts.extend(["--scope", scope])
        if scope == "project":
            parts.extend(["--project-root", shlex.quote(str(root))])
        parts.append("--apply")
        next_command = " ".join(parts)
    result = {
        "host": host,
        "scope": scope,
        "entity": None if disconnect else entity.strip(),
        "path": str(path),
        "status": "disconnected" if disconnect and apply else (
            "connected" if apply else "preview"
        ),
        "changed": changed,
        "applied": apply,
        "diff": diff,
        "next": next_command,
    }
    if _transaction_details:
        result["_transaction"] = {
            "before": before,
            "before_mode": before_mode,
            "after": after,
            "after_mode": (
                (before_mode or 0o644)
                if before_mode is not None or changed
                else None
            ),
        }
    return result


def connection_status(
    home: Path,
    host: str,
    *,
    scope: str = "project",
    project_root: str | Path = ".",
    entity: str | None = None,
) -> dict:
    if scope not in {"project", "user"}:
        raise ValueError("scope must be project or user")
    root = Path(project_root).resolve()
    if scope == "project" and not root.is_dir():
        raise ValueError(f"project root does not exist or is not a directory: {root}")
    if host == "claude-code":
        path = root / ".mcp.json" if scope == "project" else Path.home() / ".claude.json"
        config_root = root if scope == "project" else Path.home().resolve()
    elif host == "codex":
        path = (
            root / ".codex" / "config.toml"
            if scope == "project"
            else Path.home() / ".codex" / "config.toml"
        )
        config_root = root if scope == "project" else Path.home().resolve()
    else:
        raise ValueError("host must be codex or claude-code")
    entry = None
    managed = False
    error = None
    try:
        text, _ = _read_pinned_config(path, config_root)
        if host == "claude-code":
            entry = _server_entry(_load_json_config(text, path))
            managed = _managed_json_server(entry)
        else:
            entry = _managed_toml_entry(text, path)
            managed = entry is not None
    except (OSError, UnicodeError, ValueError) as exc:
        error = safe_display(str(exc))
    details = _managed_mcp_args(entry.get("args")) if isinstance(entry, dict) else None
    expected_command = os.path.abspath(sys.executable)
    interpreter_matches = (
        isinstance(entry, dict) and entry.get("command") == expected_command
    )
    home_matches = bool(details and details["home"] == str(home))
    entity_matches = bool(
        details
        and (
            entity is None
            or entity_references_match(home, details["entity"], entity)
        )
    )
    binding_mode_matches = bool(
        details
        and (
            details["entity_locked"]
            if scope == "project"
            else not details["entity_locked"]
        )
    )
    migration_required = bool(
        scope == "project"
        and managed
        and details
        and not details["entity_locked"]
        and home_matches
        and entity_matches
    )
    migration_command = None
    if migration_required:
        migration_command = (
            f"brain-ai --home {shlex.quote(str(home))} connect {host} "
            f"--entity {shlex.quote(details['entity'])} --scope project "
            f"--project-root {shlex.quote(str(root))} --apply"
        )
    configured = bool(
        managed
        and interpreter_matches
        and home_matches
        and entity_matches
        and binding_mode_matches
    )
    return {
        "host": host,
        "scope": scope,
        "config": str(path),
        "configured": configured,
        "home": str(home),
        "configured_home": details["home"] if details else None,
        "configured_entity": details["entity"] if details else None,
        "entity_locked": bool(details and details["entity_locked"]),
        "migration_required": migration_required,
        "migration_command": migration_command,
        "interpreter_matches": interpreter_matches,
        "managed_entry": managed,
        "error": error,
    }
