"""Provider-neutral MCP surface for Brain-AI memory management."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .runtime import BrainAIRuntime


class MCPUnavailableError(RuntimeError):
    """Raised when the optional MCP dependency is not installed."""


def _mcp_import():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise MCPUnavailableError(
            "MCP support is optional. Install it with: pip install 'brain-ai-memory[mcp]'"
        ) from exc
    return FastMCP


def create_mcp_server(
    home: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    default_entity: str = "",
    locked_entity: str = "",
):
    """Create an MCP server without starting a transport."""
    if default_entity and locked_entity:
        raise ValueError("use either default_entity or locked_entity, not both")
    FastMCP = _mcp_import()
    runtime = BrainAIRuntime(home)
    locked_record = runtime.store.get_entity(locked_entity) if locked_entity else None
    configured_entity = locked_entity or default_entity

    def select_entity(requested: str = "", *, required: bool = False) -> str | None:
        if locked_record:
            if requested:
                requested_record = runtime.store.get_entity(requested)
                if requested_record["id"] != locked_record["id"]:
                    raise ValueError(
                        "this project connection is locked to "
                        f"{locked_record['name']}"
                    )
            return locked_record["id"]
        selected = requested or configured_entity
        if required and not selected:
            raise ValueError(
                "entity is required when no default or locked entity is configured"
            )
        return selected or None

    server = FastMCP(
        "brain-ai-memory",
        instructions=(
            "Use brain_resume at the start of cross-session work, then brain_context "
            "before acting. Pass an entity unless this server has a configured default. "
            "A project-locked server rejects another entity. "
            "Prefer exact state over estimates, stop when a requested gate returns "
            "allowed=false, and write brain_checkpoint at handoff. "
            "MCP deliberately does not expose arbitrary command execution; execute "
            "approved actions in the host agent."
        ),
        host=host,
        port=port,
    )

    @server.tool(name="brain_context")
    def context(
        query: str,
        proposed_action: str = "",
        entity: str = "",
        limit: int = 5,
    ) -> dict:
        """Route recall, bind an optional entity, and check a proposed action."""
        return runtime.process(
            query,
            proposed_action=proposed_action or None,
            entity=select_entity(entity),
            limit=limit,
        )

    @server.tool(name="brain_check_action")
    def check_action(action: str, entity: str = "") -> dict:
        """Return the deterministic allow, warn, or block verdict for an action."""
        return runtime.gate(action, entity=select_entity(entity))

    @server.tool(name="brain_remember")
    def remember(
        kind: str,
        text: str = "",
        entity: str = "",
        source: str = "mcp",
        key: str = "",
        value_json: str = "",
        pattern: str = "",
        effect: str = "block",
        promote_to: str = "",
    ) -> dict:
        """Write an event, fact, rule, or exact state into its owned store."""
        selected_entity = select_entity(entity)
        entities = [selected_entity] if selected_entity else []
        if kind == "episodic":
            if not text:
                raise ValueError("text is required for episodic memory")
            return runtime.store.append_event(
                text,
                source=source,
                entities=entities,
                promote_to=promote_to or None,
                rule_pattern=pattern or None,
            )
        if kind == "semantic":
            if not text:
                raise ValueError("text is required for semantic memory")
            return runtime.store.put_knowledge(text, source=source, entities=entities)
        if kind == "rule":
            if not text or not pattern:
                raise ValueError("text and pattern are required for rule memory")
            return runtime.store.add_rule(
                pattern,
                effect=effect,
                reason=text,
                source=source,
                entities=entities,
            )
        if kind == "state":
            if not key or not value_json:
                raise ValueError("key and value_json are required for exact state")
            return runtime.store.set_state(
                key,
                json.loads(value_json),
                source=source,
                entity=selected_entity or None,
            )
        raise ValueError("kind must be episodic, semantic, rule, or state")

    if not locked_record:
        @server.tool(name="brain_upsert_entity")
        def upsert_entity(
            name: str,
            entity_type: str = "concept",
            aliases: list[str] | None = None,
        ) -> dict:
            """Create or resolve a stable entity used to scope memory and state."""
            return runtime.store.put_entity(
                name, entity_type=entity_type, aliases=aliases or []
            )

        @server.tool(name="brain_add_relation")
        def add_relation(
            subject: str,
            predicate: str,
            object: str,
            source: str = "mcp",
        ) -> dict:
            """Create a typed relation between two existing entities."""
            return runtime.store.add_relation(
                subject, predicate, object, source=source
            )

    @server.tool(name="brain_checkpoint")
    def checkpoint(
        summary: str = "",
        entity: str = "",
        next_actions: list[str] | None = None,
    ) -> dict:
        """Persist an entity-scoped handoff (or a legacy global checkpoint)."""
        selected_entity = select_entity(entity)
        if selected_entity:
            return runtime.handoff(
                selected_entity,
                summary=summary,
                next_actions=next_actions or [],
            )
        return runtime.checkpoint(summary)

    @server.tool(name="brain_resume")
    def resume(entity: str = "") -> dict:
        """Return the latest handoff for exactly one entity."""
        selected_entity = select_entity(entity, required=True)
        return runtime.resume(selected_entity)

    if not locked_record:
        @server.tool(name="brain_consolidation_preview")
        def consolidation_preview() -> dict:
            """Preview all episodic promotions on an unlocked administrative server."""
            return runtime.consolidate(apply=False)

    @server.tool(name="brain_supersede")
    def supersede(
        old_id: str,
        new_text: str,
        source: str = "mcp",
        entity: str = "",
    ) -> dict:
        """Replace a stale fact within one explicit or default entity scope."""
        selected_entity = select_entity(entity, required=True)
        return runtime.reconsolidate(
            old_id,
            new_text,
            source=source,
            entity=selected_entity,
        )

    @server.resource("brain-ai://status", mime_type="application/json")
    def status_resource() -> str:
        if locked_record:
            value = {
                "version": __version__,
                "entity": locked_record,
                "latest_handoff": runtime.resume(locked_record["id"]),
            }
        else:
            value = runtime.status()
        return json.dumps(value, ensure_ascii=False, indent=2)

    @server.resource("brain-ai://ontology", mime_type="application/json")
    def ontology_resource() -> str:
        return json.dumps(runtime.ontology, ensure_ascii=False, indent=2)

    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain-ai-mcp")
    parser.add_argument("--home")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--entity", default="", help="default entity scope for this MCP server")
    parser.add_argument(
        "--locked-entity",
        default="",
        help="project entity scope that tool calls cannot override",
    )
    args = parser.parse_args(argv)
    try:
        server = create_mcp_server(
            args.home,
            host=args.host,
            port=args.port,
            default_entity=args.entity,
            locked_entity=args.locked_entity,
        )
    except MCPUnavailableError as exc:
        print(f"brain-ai-mcp: {exc}", file=sys.stderr)
        return 2
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
