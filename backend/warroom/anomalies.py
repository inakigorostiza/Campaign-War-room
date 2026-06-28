"""Anomaly engine + dashboard-state aggregation over the ads_daily table.

Pure SQL + Python — deterministic, no LLM. Detects per channel+campaign
day-over-day CPA jumps and z-score outliers against the trailing baseline, and
assembles the cinematic dashboard state (KPIs, conversion particle arcs, alerts).
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass

from warroom.metrics_source import MetricsSource

# Thresholds for flagging an anomaly.
CPA_DELTA_PCT = 15.0   # day-over-day CPA change (abs %) that counts as notable
Z_THRESHOLD = 2.0      # z-score on the metric vs. its trailing baseline


@dataclass
class Anomaly:
    channel: str
    campaign: str
    country: str
    metric: str          # "cpa"
    direction: str       # "up" | "down"
    today_value: float
    baseline_value: float
    delta_pct: float
    zscore: float
    severity: str        # "critical" | "warning" | "info"
    spend: float
    conversions: int


def _severity(delta_pct: float, z: float) -> str:
    a = abs(delta_pct)
    if a >= 25 or abs(z) >= 3:
        return "critical"
    if a >= CPA_DELTA_PCT or abs(z) >= Z_THRESHOLD:
        return "warning"
    return "info"


def _cpa(spend: float, conversions: float) -> float:
    return spend / conversions if conversions else 0.0


def detect_anomalies(source: MetricsSource) -> list[Anomaly]:
    """Compare the latest day against each series' trailing baseline."""
    rows = source.query(
        "SELECT date, channel, campaign, country, spend, conversions "
        "FROM ads_daily ORDER BY date"
    )
    if not rows:
        return []

    latest_date = max(r["date"] for r in rows)

    # Group history by (channel, campaign).
    series: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        series.setdefault((r["channel"], r["campaign"]), []).append(r)

    anomalies: list[Anomaly] = []
    for (channel, campaign), hist in series.items():
        hist.sort(key=lambda r: r["date"])
        today = next((r for r in hist if r["date"] == latest_date), None)
        if not today:
            continue
        prior = [r for r in hist if r["date"] < latest_date]
        if len(prior) < 5:
            continue

        baseline_cpas = [_cpa(r["spend"], r["conversions"]) for r in prior]
        today_cpa = _cpa(today["spend"], today["conversions"])
        baseline_mean = statistics.fmean(baseline_cpas)
        if baseline_mean <= 0:
            continue

        delta_pct = (today_cpa - baseline_mean) / baseline_mean * 100.0
        stdev = statistics.pstdev(baseline_cpas)
        z = (today_cpa - baseline_mean) / stdev if stdev > 0 else 0.0

        if abs(delta_pct) >= CPA_DELTA_PCT or abs(z) >= Z_THRESHOLD:
            anomalies.append(Anomaly(
                channel=channel,
                campaign=campaign,
                country=today["country"],
                metric="cpa",
                direction="up" if delta_pct >= 0 else "down",
                today_value=round(today_cpa, 2),
                baseline_value=round(baseline_mean, 2),
                delta_pct=round(delta_pct, 1),
                zscore=round(z, 2),
                severity=_severity(delta_pct, z),
                spend=round(today["spend"], 2),
                conversions=int(today["conversions"]),
            ))

    # Worst first.
    anomalies.sort(key=lambda a: abs(a.delta_pct), reverse=True)
    return anomalies


def build_state(source: MetricsSource) -> dict:
    """Assemble the full dashboard state the frontend renders."""
    rows = source.query("SELECT * FROM ads_daily ORDER BY date")
    if not rows:
        return {"latest_date": None, "kpis": {}, "arcs": [], "channels": [], "anomalies": []}

    latest_date = max(r["date"] for r in rows)
    today_rows = [r for r in rows if r["date"] == latest_date]

    total_spend = sum(r["spend"] for r in today_rows)
    total_conv = sum(r["conversions"] for r in today_rows)
    total_rev = sum(r["revenue"] for r in today_rows)
    total_clicks = sum(r["clicks"] for r in today_rows)
    total_impr = sum(r["impressions"] for r in today_rows)

    kpis = {
        "spend": round(total_spend, 2),
        "conversions": int(total_conv),
        "revenue": round(total_rev, 2),
        "cpa": round(_cpa(total_spend, total_conv), 2),
        "roas": round(total_rev / total_spend, 2) if total_spend else 0.0,
        "ctr": round(total_clicks / total_impr * 100, 2) if total_impr else 0.0,
    }

    # Per-channel rollup for the KPI rail.
    by_channel: dict[str, dict] = {}
    for r in today_rows:
        c = by_channel.setdefault(r["channel"], {"channel": r["channel"], "spend": 0.0, "conversions": 0})
        c["spend"] += r["spend"]
        c["conversions"] += r["conversions"]
    channels = [
        {**c, "spend": round(c["spend"], 2), "cpa": round(_cpa(c["spend"], c["conversions"]), 2)}
        for c in by_channel.values()
    ]
    channels.sort(key=lambda c: c["spend"], reverse=True)

    # Conversion particle arcs: one per campaign, weighted by conversions.
    arcs = [
        {
            "channel": r["channel"],
            "campaign": r["campaign"],
            "country": r["country"],
            "startLat": r["lat"],
            "startLng": r["lng"],
            "conversions": int(r["conversions"]),
            "spend": round(r["spend"], 2),
        }
        for r in today_rows
    ]

    anomalies = [asdict(a) for a in detect_anomalies(source)]

    return {
        "latest_date": latest_date,
        "kpis": kpis,
        "channels": channels,
        "arcs": arcs,
        "anomalies": anomalies,
    }


if __name__ == "__main__":
    # Spot-check against the seed.
    from warroom.config import Settings
    from warroom.metrics_source import build_source

    src = build_source(Settings.load())
    found = detect_anomalies(src)
    print(f"Detected {len(found)} anomalies:")
    for a in found:
        print(f"  {a.severity.upper():8} {a.channel}/{a.campaign} "
              f"CPA {a.direction} {a.delta_pct:+.1f}% (z={a.zscore}) "
              f"now ${a.today_value} vs base ${a.baseline_value}")
