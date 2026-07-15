"""Portable configuration for the public runtime."""

from __future__ import annotations

import json
import os
from pathlib import Path


DEFAULT_CONFIG = {
    "schema_version": 1,
    "runtime": {"recall_limit": 5},
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
    return Path(selected).expanduser().resolve()


def write_default_config(home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    path = home / "config.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
