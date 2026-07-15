"""Read-only clean-room observer for a local Brain-AI runtime."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .runtime import BrainAIRuntime


def dashboard_html(runtime: BrainAIRuntime) -> str:
    status = runtime.status()
    counts = status["counts"]
    cards = "".join(
        f'<div class="card"><span>{html.escape(label)}</span><strong>{counts[key]}</strong></div>'
        for key, label in (
            ("episodic", "HC · Episodes"),
            ("semantic", "ATL · Knowledge"),
            ("rules", "BG · Rules"),
            ("numerical_state", "IPS · State"),
            ("entities", "HC · Entities"),
            ("relations", "HC · Relations"),
            ("audit_events", "PFC · Traces"),
            ("checkpoints", "Checkpoints"),
        )
    )
    recent = runtime.store.recent_audit(12)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(event.get('created_at', '')))}</td>"
        f"<td>{html.escape(str(event.get('event', '')))}</td>"
        f"<td>{html.escape(str(event.get('status', '')))}</td>"
        f"<td>{html.escape(', '.join(event.get('route', [])))}</td>"
        "</tr>"
        for event in reversed(recent)
    ) or '<tr><td colspan="4">No runtime events yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brain-AI Command Center</title>
<style>
:root{{--ink:#172033;--muted:#64748b;--paper:#f6f7fb;--line:#dfe5ee;--accent:#5b5ce2;--ok:#0e9f6e}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:40px 24px}} header{{display:flex;justify-content:space-between;gap:20px;align-items:end}}
h1{{font-size:30px;margin:0}} .subtitle{{color:var(--muted)}} .pill{{background:#e7f8f1;color:#087452;padding:6px 10px;border-radius:999px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:28px 0}}
.card{{background:white;border:1px solid var(--line);border-radius:14px;padding:16px;display:flex;flex-direction:column;gap:8px}}
.card span{{color:var(--muted);font-size:13px}} .card strong{{font-size:28px}} section{{background:white;border:1px solid var(--line);border-radius:14px;padding:20px}}
table{{border-collapse:collapse;width:100%}} th,td{{padding:11px;border-bottom:1px solid var(--line);text-align:left}} th{{color:var(--muted);font-size:12px;text-transform:uppercase}}
code{{background:#eef0f5;padding:2px 5px;border-radius:4px}} footer{{color:var(--muted);margin-top:18px;font-size:13px}}
</style></head><body><main>
<header><div><h1>Brain-AI Command Center</h1><div class="subtitle">Local, read-only runtime observability</div></div><div class="pill">● runtime ready</div></header>
<div class="grid">{cards}</div>
<section><h2>Recent control-loop traces</h2><table><thead><tr><th>Time</th><th>Event</th><th>Status</th><th>Components</th></tr></thead><tbody>{rows}</tbody></table></section>
<footer>Backend: <code>{html.escape(status['semantic_backend'])}</code> · Home: <code>{html.escape(status['home'])}</code> · Read-only APIs: <code>/api/status</code>, <code>/api/events</code></footer>
</main></body></html>"""


def serve(runtime: BrainAIRuntime, host: str = "127.0.0.1", port: int = 8765) -> None:
    class Handler(BaseHTTPRequestHandler):
        server_version = "BrainAIObserver/0.3"
        sys_version = ""

        def log_message(self, format, *args):
            return

        def _headers(self, content_type: str, length: int) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
            )

        def _json(self, value: dict | list, status: int = 200):
            payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self._headers("application/json; charset=utf-8", len(payload))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/api/health":
                return self._json({"status": "ok", "version": __version__})
            if self.path == "/api/status":
                return self._json(runtime.status())
            if self.path == "/api/events":
                return self._json(runtime.store.recent_audit(100))
            if self.path == "/":
                payload = dashboard_html(runtime).encode("utf-8")
                self.send_response(200)
                self._headers("text/html; charset=utf-8", len(payload))
                self.end_headers()
                return self.wfile.write(payload)
            return self._json({"error": "not found"}, 404)

        def do_HEAD(self):
            if self.path == "/":
                payload = dashboard_html(runtime).encode("utf-8")
                self.send_response(200)
                self._headers("text/html; charset=utf-8", len(payload))
                return self.end_headers()
            if self.path in {"/api/health", "/api/status", "/api/events"}:
                self.send_response(200)
                self._headers("application/json; charset=utf-8", 0)
                return self.end_headers()
            self.send_response(404)
            self._headers("application/json; charset=utf-8", 0)
            self.end_headers()

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Brain-AI Command Center: http://{host}:{port}")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print("WARNING: this reference observer has no authentication; bind to localhost unless isolated.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
