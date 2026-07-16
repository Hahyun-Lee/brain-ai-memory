"""Reference kernel for Brain-AI memory and supporting component contracts."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from . import __version__
from .adapters import build_semantic_adapter
from .config import load_config, resolve_home
from .ontology import load_ontology
from .storage import MemoryStore, new_id, utc_now
from .text import tokenize


BUILTIN_RULES = [
    (re.compile(r"\brm\s+-\w*r\w*\s+(/|~|\$HOME)(\s|$)"), "block", "recursive delete of a bare root or home directory"),
    (re.compile(r"curl[^\n|]*\|\s*(sudo\s+)?(ba)?sh\b"), "block", "download piped directly into a shell"),
    (re.compile(r"--no-verify|verify\s*=\s*False|InsecureSkipVerify"), "block", "verification bypass"),
]

NUMERIC_HINTS = re.compile(r"\b(count|number|total|metric|how many)\b|개수|몇\s*개|수치|총합", re.I)
TEMPORAL_HINTS = re.compile(r"\b(when|before|after|recent|last|timeline|session)\b|언제|이전|이후|최근|세션", re.I)
PROCEDURAL_HINTS = re.compile(r"\b(rule|must|never|always|procedure|workflow|fallback|how do)\b|규칙|절차|항상|금지|실행", re.I)


class BrainAIRuntime:
    """Provider-neutral memory-management kernel with an optional action bridge."""

    def __init__(self, home: str | Path | None = None):
        self.home = resolve_home(home)
        self.store = MemoryStore(self.home)
        self.store.initialize()
        self.config = load_config(self.home)
        self.ontology, self.ontology_summary = load_ontology()
        self.semantic = build_semantic_adapter(self.store, self.config)

    def route(self, query: str, proposed_action: str | None = None) -> list[str]:
        components: list[str] = ["PFC"]
        if proposed_action:
            components.extend(["TH", "BG"])
        if NUMERIC_HINTS.search(query):
            components.append("IPS")
        if TEMPORAL_HINTS.search(query):
            components.append("HC")
        if PROCEDURAL_HINTS.search(query):
            components.extend(["BG", "CB"])
        components.extend(["ATL", "HC"])
        return list(dict.fromkeys(components))

    def gate(self, action: str | None, *, entity: str | None = None) -> dict:
        if not action:
            return {"allowed": True, "effect": "allow", "reason": "no proposed action", "rule_id": None}
        warnings = []
        for pattern, effect, reason in BUILTIN_RULES:
            if pattern.search(action):
                if effect == "block":
                    return {"allowed": False, "effect": effect, "reason": reason, "rule_id": "builtin"}
                warnings.append(reason)
        entity_id = self.store.get_entity(entity)["id"] if entity else None
        for rule in self.store.rules():
            if rule.get("entity_ids"):
                if not entity_id or entity_id not in rule["entity_ids"]:
                    continue
            if re.search(rule["pattern"], action):
                if rule["effect"] == "block":
                    return {"allowed": False, "effect": "block", "reason": rule["reason"], "rule_id": rule["id"]}
                warnings.append(rule["reason"])
        return {
            "allowed": True,
            "effect": "warn" if warnings else "allow",
            "reason": "; ".join(warnings) if warnings else "no rule matched",
            "rule_id": None,
        }

    def recall(
        self,
        query: str,
        *,
        limit: int | None = None,
        proposed_action: str | None = None,
        entity: str | None = None,
    ) -> dict:
        limit = limit or int(self.config.get("runtime", {}).get("recall_limit", 5))
        if limit < 1:
            raise ValueError("recall limit must be positive")
        route = self.route(query, proposed_action)
        entity_record = self.store.get_entity(entity) if entity else None
        entity_id = entity_record["id"] if entity_record else None
        by_component: dict[str, list[dict]] = {}
        if "ATL" in route:
            semantic_results = self.semantic.search(
                query,
                limit,
                entity_id=entity_id,
            )
            if entity_id and not getattr(self.semantic, "includes_local_store", False):
                # External vault adapters cannot prove a Brain-AI entity
                # binding. Preserve authoritative project-scoped local memory
                # even when an external ATL backend is configured.
                local_results = self.store.search_knowledge(
                    query,
                    limit,
                    entity_id=entity_id,
                )
                semantic_results = (local_results + semantic_results)[:limit]
            by_component["ATL"] = semantic_results
        if "HC" in route:
            by_component["HC"] = self.store.search_events(query, limit, entity_id=entity_id)
        if "IPS" in route:
            by_component["IPS"] = self.store.search_states(query, limit, entity=entity_id)
        if "BG" in route:
            query_terms = set(tokenize(f"{query} {proposed_action or ''}"))
            rules = []
            for rule in self.store.rules():
                if rule.get("entity_ids"):
                    if not entity_id or entity_id not in rule["entity_ids"]:
                        continue
                rule_terms = set(tokenize(f"{rule['pattern']} {rule['reason']}"))
                if query_terms & rule_terms or (proposed_action and re.search(rule["pattern"], proposed_action)):
                    rules.append({**rule, "component": "BG", "kind": "procedural-rule"})
            by_component["BG"] = rules[:limit]
        entity_context = None
        if entity_record:
            entity_context = {
                **entity_record,
                "relations": self.store.relations(entity_record["id"]),
            }
        return {
            "query": query,
            "route": route,
            "entity": entity_context,
            "by_component": by_component,
        }

    def process(
        self,
        query: str,
        *,
        proposed_action: str | None = None,
        limit: int | None = None,
        entity: str | None = None,
    ) -> dict:
        started = time.perf_counter()
        run_id = new_id("run")
        gate = self.gate(proposed_action, entity=entity)
        recall = self.recall(
            query,
            limit=limit,
            proposed_action=proposed_action,
            entity=entity,
        )
        result = {
            "run_id": run_id,
            "status": "ready" if gate["allowed"] else "blocked",
            "query": query,
            "proposed_action": proposed_action,
            "route": recall["route"],
            "entity": recall["entity"],
            "gate": gate,
            "memory": recall["by_component"],
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "created_at": utc_now(),
        }
        self.store.append_audit({"event": "process", **result})
        return result

    def execute(
        self,
        query: str,
        command: list[str],
        *,
        timeout: float = 60,
        cwd: str | Path | None = None,
        entity: str | None = None,
    ) -> dict:
        if not command:
            raise ValueError("harness command is empty")
        prepared = self.process(
            query,
            proposed_action=" ".join(command),
            entity=entity,
        )
        if not prepared["gate"]["allowed"]:
            return prepared
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command, cwd=cwd, capture_output=True, text=True,
                timeout=timeout, shell=False, check=False,
            )
            execution = {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-100_000:],
                "stderr": completed.stderr[-100_000:],
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as exc:
            execution = {
                "returncode": None,
                "stdout": (exc.stdout or "")[-100_000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-100_000:] if isinstance(exc.stderr, str) else "",
                "timed_out": True,
            }
        prepared["execution"] = execution
        prepared["status"] = "completed" if execution["returncode"] == 0 else "failed"
        prepared["execution_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        self.store.append_audit({"event": "harness", **prepared})
        return prepared

    def execute_sequence(
        self,
        query: str,
        steps: list[list[str]],
        *,
        timeout: float = 60,
        cwd: str | Path | None = None,
        entity: str | None = None,
    ) -> dict:
        """Run explicit fallbacks until one succeeds; never rely on model persistence."""
        if not steps:
            raise ValueError("sequence has no steps")
        sequence_id = new_id("seq")
        attempts = []
        status = "failed"
        for position, command in enumerate(steps, start=1):
            result = self.execute(
                query,
                command,
                timeout=timeout,
                cwd=cwd,
                entity=entity,
            )
            attempts.append(
                {
                    "position": position,
                    "command": command,
                    "status": result["status"],
                    "gate": result["gate"],
                    "execution": result.get("execution"),
                }
            )
            if result["status"] == "blocked":
                status = "blocked"
                break
            if result["status"] == "completed":
                status = "completed"
                break
        output = {
            "sequence_id": sequence_id,
            "status": status,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "entity": self.store.get_entity(entity)["id"] if entity else None,
            "created_at": utc_now(),
        }
        self.store.append_audit({"event": "sequence", **output})
        return output

    def checkpoint(self, summary: str = "") -> dict:
        pending = [event["id"] for event in self.store.events() if event.get("promote_to")]
        record = {
            "id": new_id("ckpt"), "summary": summary.strip(),
            "counts": self.store.counts(), "pending_consolidation": pending,
            "created_at": utc_now(),
        }
        self.store.append_checkpoint(record)
        self.store.append_audit({"event": "checkpoint", **record})
        return record

    def handoff(
        self,
        entity: str,
        *,
        summary: str = "",
        next_actions: list[str] | None = None,
    ) -> dict:
        """Write a project-scoped checkpoint for a later session."""
        record_entity = self.store.get_entity(entity)
        entity_id = record_entity["id"]
        pending = [
            event["id"]
            for event in self.store.events()
            if event.get("promote_to") and entity_id in event.get("entity_ids", [])
        ]
        record = {
            "id": new_id("handoff"),
            "kind": "entity-handoff",
            "entity": {
                "id": entity_id,
                "name": record_entity["name"],
                "type": record_entity["type"],
            },
            "summary": summary.strip(),
            "next_actions": [item.strip() for item in (next_actions or []) if item.strip()],
            "counts": {
                "episodic": sum(
                    entity_id in item.get("entity_ids", []) for item in self.store.events()
                ),
                "semantic": sum(
                    entity_id in item.get("entity_ids", []) for item in self.store.knowledge()
                ),
                "rules": sum(
                    entity_id in item.get("entity_ids", []) for item in self.store.rules()
                ),
                "exact_state": len(self.store.states(entity_id, include_global=False)),
            },
            "pending_consolidation": pending,
            "created_at": utc_now(),
        }
        self.store.append_checkpoint(record)
        self.store.append_audit({"event": "entity_handoff", **record})
        return record

    def resume(self, entity: str) -> dict:
        """Read the newest handoff for exactly one entity."""
        record_entity = self.store.get_entity(entity)
        for checkpoint in reversed(self.store.checkpoints(100_000)):
            if (
                checkpoint.get("kind") == "entity-handoff"
                and checkpoint.get("entity", {}).get("id") == record_entity["id"]
            ):
                return checkpoint
        return {
            "kind": "entity-handoff",
            "status": "not_found",
            "entity": {
                "id": record_entity["id"],
                "name": record_entity["name"],
                "type": record_entity["type"],
            },
            "summary": "",
            "next_actions": [],
        }

    def consolidate(self, *, apply: bool = False) -> dict:
        candidates = []
        for event in self.store.events():
            target = event.get("promote_to")
            if target not in {"semantic", "rule"}:
                continue
            candidate = {"event_id": event["id"], "target": target, "text": event["text"]}
            if apply:
                if target == "semantic":
                    created = self.store.put_knowledge(
                        event["text"],
                        source=f"consolidated:{event['id']}",
                        tags=event.get("tags", []),
                        entities=event.get("entity_ids", []),
                    )
                    operation = "migrate-to-knowledge-base"
                else:
                    pattern = event.get("rule_pattern")
                    if not pattern:
                        candidate["status"] = "needs-rule-pattern"
                        candidates.append(candidate)
                        continue
                    created = self.store.add_rule(
                        pattern,
                        reason=event["text"],
                        source=f"consolidated:{event['id']}",
                        entities=event.get("entity_ids", []),
                    )
                    operation = "migrate-to-rules"
                self.store.record_lifecycle("episodic", event["id"], operation, "approved consolidation")
                candidate.update({"status": "applied", "created_id": created["id"]})
            else:
                candidate["status"] = "pending-approval"
            candidates.append(candidate)
        result = {"applied": apply, "candidate_count": len(candidates), "candidates": candidates, "created_at": utc_now()}
        self.store.append_audit({"event": "consolidation", **result})
        return result

    def reconsolidate(
        self,
        old_id: str,
        new_text: str,
        *,
        source: str = "user",
        tags: list[str] | None = None,
        entity: str | None = None,
    ) -> dict:
        old = self.store.get_knowledge(old_id)
        selected_entity = entity
        if not selected_entity and old.get("entity_ids"):
            if len(old["entity_ids"]) != 1:
                raise ValueError(
                    "entity is required when superseding knowledge shared by multiple scopes"
                )
            selected_entity = old["entity_ids"][0]
        if selected_entity:
            created = self.store.supersede_knowledge_for_entity(
                old_id,
                new_text,
                selected_entity,
                source=source,
                tags=tags or old.get("tags", []),
            )
        else:
            created = self.store.put_knowledge(
                new_text,
                source=source,
                tags=tags or old.get("tags", []),
                supersedes=old_id,
            )
        result = {
            "old_id": old_id,
            "new_id": created["id"],
            "status": "superseded",
            "entity": selected_entity,
            "created_at": utc_now(),
        }
        self.store.append_audit({"event": "reconsolidation", **result})
        return result

    def status(self) -> dict:
        semantic_config = self.config.get("semantic", {})
        return {
            "home": str(self.home),
            "version": __version__,
            "counts": self.store.counts(),
            "semantic_backend": semantic_config.get("backend", "local"),
            "ontology": self.ontology_summary,
            "latest_checkpoint": (self.store.checkpoints(1) or [None])[-1],
        }
