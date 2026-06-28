"""Self-contained War Room logic for Vercel serverless functions.

Serverless functions are stateless and short-lived, so there is no background
refresh thread, no persistent SQLite file, and no long-lived SSE connection.
Each request rebuilds the deterministic dataset in an in-memory SQLite, computes
state with a light live-overlay, and (for narrative) calls Claude or falls back.

This intentionally mirrors backend/warroom (seed + anomalies + narrative) but is
duplicated here so the Vercel bundle has zero cross-directory imports.
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import statistics
import time
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Dataset (mirrors backend/warroom/seed.py)
# ---------------------------------------------------------------------------
CAMPAIGNS = [
    ("Meta",   "Summer Sale",    "US", 37.77, -122.42, 1800, 0.045, 1.10),
    ("Meta",   "Retargeting",    "GB", 51.50,   -0.12,  900, 0.060, 0.95),
    ("Google", "Brand Search",   "US", 40.71,  -74.00, 1500, 0.085, 1.40),
    ("Google", "Generic Search", "DE", 52.52,   13.40, 1200, 0.040, 1.25),
    ("TikTok", "Awareness",      "ES", 40.42,   -3.70,  700, 0.030, 0.60),
    ("TikTok", "Creator Spark",  "FR", 48.85,    2.35,  650, 0.038, 0.70),
]
DAYS = 30
HUB = {"name": "HQ", "lat": 40.42, "lng": -3.70}

CPA_DELTA_PCT = 15.0
Z_THRESHOLD = 2.0


def _build_rows(today: date) -> list[tuple]:
    rng = random.Random(42)
    rows: list[tuple] = []
    for day_offset in range(DAYS, 0, -1):
        d = today - timedelta(days=day_offset)
        is_yesterday = day_offset == 1
        for channel, campaign, country, lat, lng, base_spend, base_cvr, base_cpc in CAMPAIGNS:
            spend = base_spend * rng.uniform(0.85, 1.15)
            cpc = base_cpc * rng.uniform(0.9, 1.1)
            cvr = base_cvr * rng.uniform(0.85, 1.15)
            if is_yesterday and channel == "Meta" and campaign == "Summer Sale":
                spend = base_spend * 1.10
                cpc = base_cpc * 1.23
                cvr = base_cvr
            clicks = max(1, int(spend / cpc))
            impressions = int(clicks / rng.uniform(0.02, 0.05))
            conversions = max(1, int(clicks * cvr))
            revenue = conversions * rng.uniform(45, 80)
            rows.append((d.isoformat(), channel, campaign, country, lat, lng,
                         round(spend, 2), impressions, clicks, conversions, round(revenue, 2)))
    return rows


def _memory_db(today: date) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ads_daily (date TEXT, channel TEXT, campaign TEXT, country TEXT, "
        "lat REAL, lng REAL, spend REAL, impressions INTEGER, clicks INTEGER, "
        "conversions INTEGER, revenue REAL)"
    )
    conn.executemany(
        "INSERT INTO ads_daily VALUES (?,?,?,?,?,?,?,?,?,?,?)", _build_rows(today)
    )
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Anomalies + state (mirrors backend/warroom/anomalies.py)
# ---------------------------------------------------------------------------
def _cpa(spend: float, conversions: float) -> float:
    return spend / conversions if conversions else 0.0


def _severity(delta_pct: float, z: float) -> str:
    a = abs(delta_pct)
    if a >= 25 or abs(z) >= 3:
        return "critical"
    if a >= CPA_DELTA_PCT or abs(z) >= Z_THRESHOLD:
        return "warning"
    return "info"


def _detect_anomalies(conn: sqlite3.Connection) -> list[dict]:
    rows = [dict(r) for r in conn.execute(
        "SELECT date, channel, campaign, country, spend, conversions FROM ads_daily ORDER BY date")]
    if not rows:
        return []
    latest = max(r["date"] for r in rows)
    series: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        series.setdefault((r["channel"], r["campaign"]), []).append(r)

    out: list[dict] = []
    for (channel, campaign), hist in series.items():
        hist.sort(key=lambda r: r["date"])
        today = next((r for r in hist if r["date"] == latest), None)
        prior = [r for r in hist if r["date"] < latest]
        if not today or len(prior) < 5:
            continue
        base = [_cpa(r["spend"], r["conversions"]) for r in prior]
        tcpa = _cpa(today["spend"], today["conversions"])
        mean = statistics.fmean(base)
        if mean <= 0:
            continue
        delta = (tcpa - mean) / mean * 100.0
        sd = statistics.pstdev(base)
        z = (tcpa - mean) / sd if sd > 0 else 0.0
        if abs(delta) >= CPA_DELTA_PCT or abs(z) >= Z_THRESHOLD:
            out.append({
                "channel": channel, "campaign": campaign, "country": today["country"],
                "metric": "cpa", "direction": "up" if delta >= 0 else "down",
                "today_value": round(tcpa, 2), "baseline_value": round(mean, 2),
                "delta_pct": round(delta, 1), "zscore": round(z, 2),
                "severity": _severity(delta, z),
                "spend": round(today["spend"], 2), "conversions": int(today["conversions"]),
            })
    out.sort(key=lambda a: abs(a["delta_pct"]), reverse=True)
    return out


def build_state() -> dict:
    """Full dashboard state with a small live overlay + a time-bucketed version."""
    today = date.today()
    conn = _memory_db(today)
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM ads_daily ORDER BY date")]
        latest = max(r["date"] for r in rows)
        today_rows = [r for r in rows if r["date"] == latest]

        f = random.uniform(0.97, 1.06)  # live wobble so KPIs breathe per request
        total_spend = sum(r["spend"] for r in today_rows) * f
        total_conv = int(sum(r["conversions"] for r in today_rows) * f)
        total_rev = sum(r["revenue"] for r in today_rows) * f
        total_clicks = sum(r["clicks"] for r in today_rows)
        total_impr = sum(r["impressions"] for r in today_rows)

        kpis = {
            "spend": round(total_spend, 2),
            "conversions": total_conv,
            "revenue": round(total_rev, 2),
            "cpa": round(_cpa(total_spend, total_conv), 2),
            "roas": round(total_rev / total_spend, 2) if total_spend else 0.0,
            "ctr": round(total_clicks / total_impr * 100, 2) if total_impr else 0.0,
        }

        by_channel: dict[str, dict] = {}
        for r in today_rows:
            c = by_channel.setdefault(r["channel"], {"channel": r["channel"], "spend": 0.0, "conversions": 0})
            c["spend"] += r["spend"]
            c["conversions"] += r["conversions"]
        channels = [{**c, "spend": round(c["spend"], 2),
                     "cpa": round(_cpa(c["spend"], c["conversions"]), 2)} for c in by_channel.values()]
        channels.sort(key=lambda c: c["spend"], reverse=True)

        arcs = [{
            "channel": r["channel"], "campaign": r["campaign"], "country": r["country"],
            "startLat": r["lat"], "startLng": r["lng"],
            "conversions": int(r["conversions"]), "spend": round(r["spend"], 2),
        } for r in today_rows]

        refresh = int(os.getenv("REFRESH_SECONDS", "20")) or 20
        version = int(time.time() // refresh)  # changes every `refresh` seconds

        return {
            "latest_date": latest, "kpis": kpis, "channels": channels, "arcs": arcs,
            "anomalies": _detect_anomalies(conn), "hub": HUB,
            "version": version, "source": "seed", "refresh_reason": "serverless",
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Narrative (mirrors backend/warroom/narrative.py)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are the lead analyst in a real-time marketing war room. You receive "
    "pre-computed anomaly facts (already verified — do not recompute or doubt the "
    "numbers). Write a punchy situational briefing for a CMO watching a live "
    "dashboard.\n\n"
    "Rules:\n"
    "- Lead with the single most important movement in one sentence.\n"
    "- Name the channel, campaign, metric, and exact % change.\n"
    "- Offer one plausible cause and one concrete next action per critical item.\n"
    "- Be concise: 3-5 short sentences total, no preamble, no bullet headers. "
    "Plain text. Confident, calm, control-room tone.\n"
    "- If there are no anomalies, say the channels are stable and give the headline KPI."
)


def _fallback_briefing(state: dict) -> str:
    anomalies = state.get("anomalies", [])
    k = state.get("kpis", {})
    if not anomalies:
        return (f"All channels stable for {state.get('latest_date')}. "
                f"Spend ${k.get('spend', 0):,.0f}, {k.get('conversions', 0)} conversions, "
                f"blended CPA ${k.get('cpa', 0):,.2f}, ROAS {k.get('roas', 0):.2f}x.")
    t = anomalies[0]
    arrow = "spiked" if t["direction"] == "up" else "dropped"
    return (f"{t['channel']} {arrow} on {t['campaign']}: CPA {arrow} "
            f"{t['delta_pct']:+.0f}% to ${t['today_value']:.2f} (baseline ${t['baseline_value']:.2f}, "
            f"z={t['zscore']}). Likely an auction-cost shift in {t['country']}; "
            f"review bids and creative on this campaign. "
            f"Blended CPA ${k.get('cpa', 0):,.2f}, ROAS {k.get('roas', 0):.2f}x across all channels.")


def briefing_text(state: dict) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_briefing(state)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        model = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
        facts = json.dumps({
            "date": state.get("latest_date"), "kpis": state.get("kpis", {}),
            "anomalies": state.get("anomalies", []), "channels": state.get("channels", []),
        }, indent=2)
        msg = client.messages.create(
            model=model, max_tokens=600, thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content":
                       "Here are the verified anomaly facts and KPIs. Write the briefing.\n\n" + facts}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or _fallback_briefing(state)
    except Exception as exc:
        return _fallback_briefing(state) + f"\n\n(Live narrative unavailable: {exc})"
