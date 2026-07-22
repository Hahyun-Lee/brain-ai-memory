"""Portable configuration for the public runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .privacy import create_private_file, ensure_private_directory


DEFAULT_CONFIG = {
    "schema_version": 1,
    "runtime": {"recall_limit": 5},
    "autoloop": {
        "max_context_bytes": 6000,
        "max_record_bytes": 900,
        "capture_raw_prompt": False,
        "capture_raw_tool_output": False,
        "auto_store_artifact_events": True,
        "monitor_import_sources": True,
    },
    "semantic": {
        "backend": "local",
        "vault_path": None,
        "mcp_command": [],
        "timeout_seconds": 20,
        "merge_local_vault": True,
    },
    "observer": {"host": "127.0.0.1", "port": 8765},
}


def resolve_home(value: str | Path | None = None) -> Path:
    selected = value or os.environ.get("BRAIN_AI_HOME") or ".brain-ai"
    lexical = Path(os.path.abspath(Path(selected).expanduser()))
    if lexical.is_symlink():
        raise ValueError(f"refusing to use a symbolic-link runtime directory: {lexical}")
    resolved = lexical.resolve()
    if lexical.is_symlink():
        raise ValueError(f"refusing to use a symbolic-link runtime directory: {lexical}")
    return resolved


def write_default_config(home: Path) -> Path:
    ensure_private_directory(home)
    path = home / "config.json"
    payload = (json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    create_private_file(path, payload)
    return path


def load_config(home: Path) -> dict:
    path = write_default_config(home)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    for section, value in loaded.items():
        if isinstance(value, dict) and isinstance(config.get(section), dict):
            config[section].update(value)
        else:
            config[section] = value
    return config
