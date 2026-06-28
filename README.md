# War Room — Real-time Marketing Mission Control

A cinematic "mission control" dashboard for multichannel marketing: a 3D globe
with conversions flowing as particle arcs, "breathing" anomaly alerts, and a
live **Claude**-generated analyst briefing ("Meta spiked on Summer Sale: CPA
+24%…"). Data is ingested via **Coupler.io**.

```
Coupler.io flows ─(15 min)─▶ SQLite snapshot ◀── Coupler MCP (get-data SQL)
        │ outgoing webhook                              ▲
        ▼                                               │ MetricsSource adapter
 POST /api/webhook/coupler ─▶ Flask backend ────────────┘
                               • SQL metrics  • anomaly engine (z-score/DoD)
                               • Claude narrative (Anthropic SDK)  • SSE push
                               ▼
                  Vite + React + Three.js dashboard (react-globe.gl + GSAP)
```

## How Coupler.io fits

Coupler.io is the **ingestion layer**, not a streaming API:

- Its **MCP server** (`railsware/coupler-io-mcp-server`) exposes read-only SQL
  (`get-data`) over a SQLite snapshot of a data flow. The backend issues that
  same SQL against either the live MCP server **or** a local seed SQLite with an
  identical schema — that's the adapter seam (`warroom/metrics_source.py`).
- Its **outgoing webhook** (run-completed) hits `POST /api/webhook/coupler`,
  which recomputes state and broadcasts a refresh over SSE.

`WARROOM_SOURCE=seed` runs the whole thing on local sample data (with an injected
Meta/Summer-Sale CPA spike). Flip to `WARROOM_SOURCE=coupler` + a
`COUPLER_ACCESS_TOKEN` to read live flows via MCP — no other code changes.

## Run it

### Backend (Flask, :5001)

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                 # or: pip install flask flask-cors python-dotenv "anthropic[mcp]" mcp
cp .env.example .env             # add ANTHROPIC_API_KEY for live Claude narrative
python -m warroom.seed           # build data/sample_metrics.db
python -m warroom.app            # serves on :5001
```

Without `ANTHROPIC_API_KEY` the narrative falls back to a deterministic briefing,
so the demo runs offline.

### Frontend (Vite, :5173)

```bash
cd frontend
npm install
npm run dev                      # proxies /api -> :5001
```

Open <http://localhost:5173>. Append `?snapshot=1` for a static, no-stream render
(useful for thumbnails / headless screenshots).

## API

| Method | Path                    | Purpose                                              |
|--------|-------------------------|------------------------------------------------------|
| GET    | `/api/health`           | liveness + source/model info                         |
| GET    | `/api/state`            | current dashboard state (KPIs, arcs, anomalies)      |
| GET    | `/api/stream`           | SSE: `state`, `pulse` (conversion particles), `refresh` |
| POST   | `/api/narrative`        | SSE: `token` chunks of the Claude briefing           |
| POST   | `/api/webhook/coupler`  | Coupler outgoing webhook → refresh + broadcast       |

## Layout

```
backend/warroom/   config · metrics_source · seed · anomalies · narrative · app
frontend/src/      App · hooks/useWarRoomStream · components/{Globe,KpiRail,AnomalyCards,NarrativePanel,ErrorBoundary}
```

## Notes

- Narrative model defaults to `claude-opus-4-8` (set `CLAUDE_MODEL` to override,
  e.g. `claude-sonnet-4-6` for cheaper/faster briefings).
- The globe needs WebGL; an error boundary degrades to a static ring where WebGL
  is unavailable so the rest of the dashboard always renders.
