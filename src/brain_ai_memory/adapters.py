"""Semantic-memory adapters, including Smart Connections MCP compatibility."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .storage import MemoryStore
from .text import ranked


SKIP_VAULT_DIRS = {".git", ".obsidian", ".smart-env", ".trash", "node_modules"}


class LocalSemanticAdapter:
    name = "local-bm25"

    def __init__(self, store: MemoryStore):
        self.store = store

    def search(self, query: str, limit: int = 5) -> list[dict]:
        return self.store.search_knowledge(query, limit)


class VaultBM25Adapter:
    """Fast, model-free vault fallback that also sees plugin-unindexed notes."""

    name = "vault-bm25"

    def __init__(self, vault_path: str | Path):
        self.vault_path = Path(vault_path).expanduser().resolve()

    def _documents(self) -> list[dict]:
        if not self.vault_path.is_dir():
            return []
        documents = []
        for path in self.vault_path.rglob("*.md"):
            try:
                relative = path.relative_to(self.vault_path)
            except ValueError:
                continue
            if any(part in SKIP_VAULT_DIRS or part.startswith(".") for part in relative.parts[:-1]):
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            documents.append(
                {
                    "id": f"vault:{relative.as_posix()}",
                    "path": relative.as_posix(),
                    "text": content,
                    "source": str(path),
                    "component": "ATL",
                    "kind": "semantic",
                    "backend": self.name,
                }
            )
        return documents

    def search(self, query: str, limit: int = 5) -> list[dict]:
        return ranked(self._documents(), query, limit=limit)


class MCPProtocolError(RuntimeError):
    pass


class MCPStdioClient:
    """Small JSONL MCP client used only for the optional semantic adapter."""

    def __init__(self, command: list[str], env: dict[str, str], timeout: float = 20):
        if not command:
            raise ValueError("mcp_command is empty")
        self.command = command
        self.env = env
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self.next_id = 1
        self.messages: queue.Queue[dict] = queue.Queue()

    def __enter__(self):
        executable = shutil.which(self.command[0]) or (self.command[0] if Path(self.command[0]).exists() else None)
        if not executable:
            raise FileNotFoundError(f"MCP executable not found: {self.command[0]}")
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env={**os.environ, **self.env},
        )
        threading.Thread(target=self._read_messages, daemon=True).start()
        try:
            self.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "brain-ai-memory", "version": "0.3.0"},
                },
            )
            self.notify("notifications/initialized", {})
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        if self.process:
            if self.process.stdin:
                self.process.stdin.close()
            if self.process.stdout:
                self.process.stdout.close()

    def _write(self, message: dict) -> None:
        if not self.process or not self.process.stdin:
            raise MCPProtocolError("MCP process is not running")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _read_messages(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self.messages.put(message)

    def _read_for_id(self, request_id: int) -> dict:
        if not self.process:
            raise MCPProtocolError("MCP process is not running")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None and self.messages.empty():
                raise MCPProtocolError(f"MCP process exited with {self.process.returncode}")
            remaining = max(0.01, deadline - time.monotonic())
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise MCPProtocolError(str(message["error"]))
            return message.get("result", {})
        raise TimeoutError(f"MCP request timed out after {self.timeout:g}s")

    def request(self, method: str, params: dict) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return self._read_for_id(request_id)

    def notify(self, method: str, params: dict) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})


class SmartConnectionsAdapter:
    """MCP semantic search with multilingual, unindexed-vault fallback.

    The fallback is deliberate: an embedding server may be cold, unavailable,
    or behind the files currently present in the vault. Every hit names its
    backend so callers can audit which path answered the query.
    """

    name = "smart-connections-hybrid"

    def __init__(self, vault_path: str | Path, command: list[str], timeout: float = 20, merge_local: bool = True):
        self.vault_path = Path(vault_path).expanduser().resolve()
        self.command = command
        self.timeout = timeout
        self.merge_local = merge_local
        self.fallback = VaultBM25Adapter(self.vault_path)
        self.last_diagnostic: dict = {}
        self._server_hybrid = False

    def _mcp_search(self, query: str, limit: int) -> list[dict]:
        started = time.perf_counter()
        with MCPStdioClient(
            self.command,
            {"SMART_VAULT_PATH": str(self.vault_path)},
            self.timeout,
        ) as client:
            result = client.request(
                "tools/call",
                {"name": "search_notes", "arguments": {"query": query, "limit": limit, "threshold": 0}},
            )
        content = result.get("content", [])
        text = next((item.get("text", "") for item in content if item.get("type") == "text"), "[]")
        raw = json.loads(text)
        if isinstance(raw, dict):
            raw_hits = raw.get("results", [])
            mode = raw.get("mode")
            profile = raw.get("profile")
            warning = raw.get("warning")
        else:
            raw_hits = raw
            mode = None
            profile = None
            warning = None
        self._server_hybrid = profile in {"fast", "balanced", "adaptive", "quality"}
        hits = []
        for position, item in enumerate(raw_hits if isinstance(raw_hits, list) else []):
            if not isinstance(item, dict):
                continue
            note_path = str(item.get("path", ""))
            if not note_path:
                continue
            full_path = (self.vault_path / note_path).resolve()
            note_text = str(item.get("snippet", ""))
            try:
                full_path.relative_to(self.vault_path)
                if not note_text and full_path.is_file():
                    note_text = full_path.read_text(encoding="utf-8", errors="replace")[:4_000]
            except (OSError, ValueError):
                note_text = ""
            hits.append(
                {
                    "id": f"vault:{note_path}", "path": note_path,
                    "text": note_text, "source": str(full_path),
                    "score": float(item.get("similarity", item.get("score", 1 / (position + 1)))),
                    "component": "ATL", "kind": "semantic", "backend": "smart-connections-mcp",
                    "vault": item.get("vault"), "scope": item.get("scope"),
                    "block": item.get("block"), "retrieval": item.get("retrieval", []),
                    "score_type": item.get("scoreType"),
                }
            )
        self.last_diagnostic = {
            "mcp": "ok", "mcp_hits": len(hits),
            "mcp_mode": mode, "mcp_profile": profile, "mcp_warning": warning,
            "server_hybrid": self._server_hybrid,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        return hits

    def search(self, query: str, limit: int = 5) -> list[dict]:
        started = time.perf_counter()
        mcp_hits: list[dict] = []
        error = None
        try:
            mcp_hits = self._mcp_search(query, limit)
        except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        # v2 hybrid profiles already discover disk-only Markdown and include a
        # BM25 leg. Repeating local BM25 would double-count the same evidence
        # and alter the server's measured ranking. Keep the local merge for v1,
        # upstream `plugin` profile, and MCP failures.
        local_hits = (
            self.fallback.search(query, limit)
            if (not mcp_hits or (self.merge_local and not self._server_hybrid))
            else []
        )
        if mcp_hits and not local_hits:
            output = mcp_hits[:limit]
            self.last_diagnostic.update(
                {
                    "fallback_hits": 0, "error": error,
                    "returned": len(output),
                    "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "fusion": "server-ranked",
                }
            )
            return output
        # Cosine and BM25 scores are not calibrated to the same scale. Fuse
        # ranks instead of letting the numerically larger backend dominate.
        merged: dict[str, dict] = {}
        for result_list in (mcp_hits, local_hits):
            for rank, hit in enumerate(result_list, start=1):
                key = str(hit.get("path") or hit.get("id"))
                backend = str(hit.get("backend", "unknown"))
                if key not in merged:
                    merged[key] = {
                        **hit,
                        "fusion_score": 0.0,
                        "raw_scores": {},
                        "backends": [],
                    }
                record = merged[key]
                record["fusion_score"] += 1 / (60 + rank)
                record["raw_scores"][backend] = hit.get("score")
                if backend not in record["backends"]:
                    record["backends"].append(backend)
                if not record.get("text") and hit.get("text"):
                    record["text"] = hit["text"]
        output = sorted(
            merged.values(),
            key=lambda item: (-float(item["fusion_score"]), str(item.get("id", ""))),
        )[:limit]
        for item in output:
            item["score"] = round(float(item.pop("fusion_score")), 8)
            item["backend"] = "+".join(item.pop("backends"))
        self.last_diagnostic.update(
            {
                "fallback_hits": len(local_hits), "error": error,
                "returned": len(output),
                "total_latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "fusion": "reciprocal-rank",
            }
        )
        return output


def build_semantic_adapter(store: MemoryStore, config: dict):
    semantic = config.get("semantic", {})
    backend = semantic.get("backend", "local")
    vault_path = semantic.get("vault_path")
    if backend == "local":
        return LocalSemanticAdapter(store)
    if backend == "vault-bm25":
        if not vault_path:
            raise ValueError("semantic.vault_path is required for vault-bm25")
        return VaultBM25Adapter(vault_path)
    if backend == "smart-connections":
        if not vault_path:
            raise ValueError("semantic.vault_path is required for smart-connections")
        return SmartConnectionsAdapter(
            vault_path,
            list(semantic.get("mcp_command") or []),
            float(semantic.get("timeout_seconds", 20)),
            bool(semantic.get("merge_local_vault", True)),
        )
    raise ValueError(f"unknown semantic backend: {backend}")
