"""Flask backend: dashboard state, live SSE pulse, Claude narrative, Coupler webhook.

Endpoints
  GET  /api/state            -> current dashboard state (one-shot JSON)
  GET  /api/stream           -> SSE: `state`, `pulse` (conversion particles), `refresh`
  POST /api/narrative        -> SSE: `token` chunks of the Claude briefing, then `done`
  POST /api/webhook/coupler  -> Coupler outgoing webhook: trigger a refresh + broadcast
  GET  /api/health           -> liveness + source/model info
"""

from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Iterator

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from warroom import narrative
from warroom.anomalies import build_state
from warroom.config import Settings
from warroom.metrics_source import build_source
from warroom.seed import HUB


class Hub:
    """Shared, thread-safe holder for the latest dashboard state + a version counter."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.source = build_source(settings)
        self._lock = threading.Lock()
        self.version = 0
        self.state: dict = {}
        self.refresh(reason="startup")

    def refresh(self, reason: str = "scheduled") -> dict:
        """Recompute state from the source, apply a small live overlay, bump version."""
        base = build_state(self.source)
        state = _apply_live_overlay(base)
        state["hub"] = HUB
        state["source"] = self.settings.source
        with self._lock:
            self.version += 1
            state["version"] = self.version
            state["refresh_reason"] = reason
            self.state = state
        return state

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.state)


def _apply_live_overlay(state: dict) -> dict:
    """Nudge today's figures so the dashboard breathes between refreshes.

    The seed DB is deterministic; this multiplicative wobble simulates intraday
    data arriving on each Coupler refresh without rewriting the underlying data.
    """
    f = random.uniform(0.97, 1.06)
    kpis = state.get("kpis", {})
    if kpis:
        kpis["spend"] = round(kpis["spend"] * f, 2)
        kpis["conversions"] = int(kpis["conversions"] * f)
        kpis["revenue"] = round(kpis["revenue"] * f, 2)
        kpis["cpa"] = round(kpis["spend"] / kpis["conversions"], 2) if kpis["conversions"] else 0.0
        kpis["roas"] = round(kpis["revenue"] / kpis["spend"], 2) if kpis["spend"] else 0.0
    for arc in state.get("arcs", []):
        arc["conversions"] = max(1, int(arc["conversions"] * random.uniform(0.95, 1.08)))
    return state


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _pulse_pings(state: dict, max_pings: int = 6) -> list[dict]:
    """Sample conversion 'pings' weighted by each campaign's conversions -> particle arcs."""
    arcs = state.get("arcs", [])
    if not arcs:
        return []
    weights = [max(1, a["conversions"]) for a in arcs]
    n = random.randint(2, max_pings)
    chosen = random.choices(arcs, weights=weights, k=n)
    pings = []
    for a in chosen:
        pings.append({
            "channel": a["channel"],
            "campaign": a["campaign"],
            "country": a["country"],
            "startLat": a["startLat"],
            "startLng": a["startLng"],
            "value": round(random.uniform(45, 90), 2),  # conversion value
        })
    return pings


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.load()
    app = Flask(__name__)
    CORS(app)
    hub = Hub(settings)

    # Background "Coupler refresh" timer (simulates the 15-min cadence in seed mode).
    def _refresher():
        while True:
            time.sleep(max(5, settings.refresh_seconds))
            try:
                hub.refresh(reason="scheduled")
            except Exception as exc:  # keep the loop alive
                print(f"[refresher] error: {exc}")

    threading.Thread(target=_refresher, daemon=True).start()

    @app.route("/api/health")
    def health():
        return jsonify({
            "ok": True,
            "source": settings.source,
            "model": settings.claude_model,
            "has_anthropic": settings.has_anthropic,
            "version": hub.version,
        })

    @app.route("/api/state")
    def state():
        return jsonify(hub.snapshot())

    @app.route("/api/stream")
    def stream():
        def gen() -> Iterator[str]:
            last_version = -1
            # Send current state immediately on connect.
            snap = hub.snapshot()
            last_version = snap.get("version", 0)
            yield _sse("state", snap)

            while True:
                snap = hub.snapshot()
                # A refresh landed -> tell the UI to flash + re-pull narrative.
                if snap.get("version", 0) != last_version:
                    last_version = snap["version"]
                    yield _sse("refresh", {"version": last_version,
                                           "reason": snap.get("refresh_reason")})
                    yield _sse("state", snap)
                # Frequent conversion pulses for the globe particles.
                yield _sse("pulse", {"pings": _pulse_pings(snap)})
                time.sleep(1.0)

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    @app.route("/api/narrative", methods=["POST", "GET"])
    def api_narrative():
        snap = hub.snapshot()

        def gen() -> Iterator[str]:
            for chunk in narrative.stream_briefing(settings, snap):
                yield _sse("token", {"text": chunk})
            yield _sse("done", {"version": snap.get("version")})

        return Response(gen(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    @app.route("/api/webhook/coupler", methods=["POST"])
    def coupler_webhook():
        # Coupler's outgoing webhook fires when a data-flow run completes.
        # (Optional: verify a shared secret / HMAC here before trusting it.)
        payload = request.get_json(silent=True) or {}
        hub.refresh(reason="coupler_webhook")
        return jsonify({"ok": True, "version": hub.version, "received": bool(payload)})

    return app


# `flask --app warroom.app run` entry point.
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, threaded=True)
