"""Load and validate the executable Brain-AI component ontology."""

from __future__ import annotations

import os
import sysconfig
from pathlib import Path

import yaml


REQUIRED_COMPONENT_FIELDS = {
    "id",
    "function",
    "construct",
    "store",
    "software_adaptation",
    "failure_mode",
    "diagnostic",
}
REQUIRED_CHANNEL_FIELDS = {"id", "direction", "function", "failure_mode"}


def ontology_path(explicit: str | Path | None = None) -> Path:
    """Resolve the canonical schema in source checkouts and installed wheels."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("BRAIN_AI_ONTOLOGY"):
        candidates.append(Path(os.environ["BRAIN_AI_ONTOLOGY"]).expanduser())
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "schema" / "brain_components.yaml",
            Path(sysconfig.get_path("data"))
            / "share"
            / "brain-ai-memory"
            / "schema"
            / "brain_components.yaml",
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    rendered = "\n".join(f"- {candidate}" for candidate in candidates)
    raise FileNotFoundError(f"Brain-AI ontology not found. Checked:\n{rendered}")


def validate_ontology(data: dict) -> dict:
    """Fail fast when component contracts are incomplete or ambiguous."""
    if not isinstance(data, dict) or not isinstance(data.get("version"), int):
        raise ValueError("ontology must contain an integer version")
    components = data.get("components")
    channels = data.get("channels")
    if not isinstance(components, list) or not components:
        raise ValueError("ontology must contain components")
    if not isinstance(channels, list) or not channels:
        raise ValueError("ontology must contain channels")

    component_ids: list[str] = []
    for position, component in enumerate(components):
        if not isinstance(component, dict):
            raise ValueError(f"component {position} must be an object")
        missing = REQUIRED_COMPONENT_FIELDS - component.keys()
        if missing:
            raise ValueError(
                f"component {component.get('id', position)} is missing: {', '.join(sorted(missing))}"
            )
        component_ids.append(str(component["id"]))
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("component ids must be unique")

    channel_ids: list[str] = []
    for position, channel in enumerate(channels):
        if not isinstance(channel, dict):
            raise ValueError(f"channel {position} must be an object")
        missing = REQUIRED_CHANNEL_FIELDS - channel.keys()
        if missing:
            raise ValueError(
                f"channel {channel.get('id', position)} is missing: {', '.join(sorted(missing))}"
            )
        channel_ids.append(str(channel["id"]))
    if len(channel_ids) != len(set(channel_ids)):
        raise ValueError("channel ids must be unique")

    return {
        "version": data["version"],
        "component_ids": component_ids,
        "channel_ids": channel_ids,
        "component_count": len(component_ids),
        "channel_count": len(channel_ids),
    }


def load_ontology(path: str | Path | None = None) -> tuple[dict, dict]:
    resolved = ontology_path(path)
    loaded = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    summary = validate_ontology(loaded)
    summary["path"] = str(resolved)
    return loaded, summary


def component_contract(data: dict, component_id: str) -> dict:
    for component in data["components"]:
        if component["id"] == component_id:
            return component
    raise KeyError(f"unknown component id: {component_id}")
