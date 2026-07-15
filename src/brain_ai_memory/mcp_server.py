"""Provider-neutral MCP surface for the Brain-AI control layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import BrainAIRuntime


def _mcp_import():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise RuntimeError(
            "MCP support is optional. Install it with: pip install 'brain-ai-memory[mcp]'"
        ) from exc
    return FastMCP


def create_mcp_server(
    home: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
):
    """Create an MCP server without starting a transport."""
    FastMCP = _mcp_import()
    runtime = BrainAIRuntime(home)
    server = FastMCP(
        "brain-ai-memory",
        instructions=(
            "Use brain_context before acting across sessions. Treat exact state and "
            "gate verdicts as authoritative. MCP deliberately does not expose arbitrary "
            "command execution; execute approved actions in the host agent."
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
            entity=entity or None,
            limit=limit,
        )

    @server.tool(name="brain_check_action")
    def check_action(action: str, entity: str = "") -> dict:
        """Return the deterministic allow, warn, or block verdict for an action."""
        return runtime.gate(action, entity=entity or None)

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
        entities = [entity] if entity else []
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
                entity=entity or None,
            )
        raise ValueError("kind must be episodic, semantic, rule, or state")

    @server.tool(name="brain_upsert_entity")
    def upsert_entity(
        name: str,
        entity_type: str = "concept",
        aliases: list[str] | None = None,
    ) -> dict:
        """Create or resolve a stable entity used to scope memory and state."""
        return runtime.store.put_entity(name, entity_type=entity_type, aliases=aliases or [])

    @server.tool(name="brain_add_relation")
    def add_relation(subject: str, predicate: str, object: str, source: str = "mcp") -> dict:
        """Create a typed relation between two existing entities."""
        return runtime.store.add_relation(subject, predicate, object, source=source)

    @server.tool(name="brain_checkpoint")
    def checkpoint(summary: str = "") -> dict:
        """Persist a handoff checkpoint and list pending consolidation candidates."""
        return runtime.checkpoint(summary)

    @server.tool(name="brain_consolidation_preview")
    def consolidation_preview() -> dict:
        """Preview episodic promotions; application remains an explicit local action."""
        return runtime.consolidate(apply=False)

    @server.tool(name="brain_supersede")
    def supersede(old_id: str, new_text: str, source: str = "mcp") -> dict:
        """Version a stale fact while preserving its provenance."""
        return runtime.reconsolidate(old_id, new_text, source=source)

    @server.resource("brain-ai://status", mime_type="application/json")
    def status_resource() -> str:
        return json.dumps(runtime.status(), ensure_ascii=False, indent=2)

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
    args = parser.parse_args(argv)
    server = create_mcp_server(args.home, host=args.host, port=args.port)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
