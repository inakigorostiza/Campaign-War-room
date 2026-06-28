"""Build a local SQLite snapshot of multichannel ad metrics.

The schema mirrors what the Coupler.io MCP `get-data` tool returns for a
marketing data flow, so the rest of the backend issues identical SQL against
either source. One channel/campaign gets an injected CPA spike "yesterday" so
the full anomaly -> narrative pipeline has something to light up.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from warroom.config import Settings

# (channel, campaign, country, lat, lng, base_spend/day, base_cvr, base_cpc)
CAMPAIGNS = [
    ("Meta",   "Summer Sale",      "US", 37.77, -122.42, 1800, 0.045, 1.10),
    ("Meta",   "Retargeting",      "GB", 51.50,   -0.12,  900, 0.060, 0.95),
    ("Google", "Brand Search",     "US", 40.71,  -74.00, 1500, 0.085, 1.40),
    ("Google", "Generic Search",   "DE", 52.52,   13.40, 1200, 0.040, 1.25),
    ("TikTok", "Awareness",        "ES", 40.42,   -3.70,  700, 0.030, 0.60),
    ("TikTok", "Creator Spark",    "FR", 48.85,    2.35,  650, 0.038, 0.70),
]

DAYS = 30
HUB = {"name": "HQ", "lat": 40.42, "lng": -3.70}  # Madrid HQ — arc destination

SCHEMA = """
CREATE TABLE ads_daily (
    date         TEXT    NOT NULL,
    channel      TEXT    NOT NULL,
    campaign     TEXT    NOT NULL,
    country      TEXT    NOT NULL,
    lat          REAL    NOT NULL,
    lng          REAL    NOT NULL,
    spend        REAL    NOT NULL,
    impressions  INTEGER NOT NULL,
    clicks       INTEGER NOT NULL,
    conversions  INTEGER NOT NULL,
    revenue      REAL    NOT NULL
);
"""


def _build_rows(today: date) -> list[tuple]:
    rng = random.Random(42)  # deterministic seed for reproducible demos
    rows: list[tuple] = []

    for day_offset in range(DAYS, 0, -1):
        d = today - timedelta(days=day_offset)
        is_yesterday = day_offset == 1

        for channel, campaign, country, lat, lng, base_spend, base_cvr, base_cpc in CAMPAIGNS:
            # Normal daily wobble.
            spend = base_spend * rng.uniform(0.85, 1.15)
            cpc = base_cpc * rng.uniform(0.9, 1.1)
            cvr = base_cvr * rng.uniform(0.85, 1.15)

            # Injected anomaly: Meta "Summer Sale" CPA spikes ~23% yesterday,
            # driven almost entirely by a rising CPC. Use the clean base values
            # (no wobble) so the spike reads as a believable ~+23% vs baseline.
            if is_yesterday and channel == "Meta" and campaign == "Summer Sale":
                spend = base_spend * 1.10        # a bit more spend chasing the same demand
                cpc = base_cpc * 1.23            # auction got more expensive
                cvr = base_cvr                    # conversion rate roughly flat

            clicks = max(1, int(spend / cpc))
            impressions = int(clicks / rng.uniform(0.02, 0.05))
            conversions = max(1, int(clicks * cvr))
            revenue = conversions * rng.uniform(45, 80)

            rows.append((
                d.isoformat(), channel, campaign, country, lat, lng,
                round(spend, 2), impressions, clicks, conversions, round(revenue, 2),
            ))
    return rows


def build_db(db_path: Path, today: date | None = None) -> int:
    """(Re)build the seed SQLite DB. Returns the number of rows written."""
    today = today or date.today()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    rows = _build_rows(today)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO ads_daily "
            "(date, channel, campaign, country, lat, lng, spend, impressions, "
            " clicks, conversions, revenue) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main() -> None:
    settings = Settings.load()
    n = build_db(settings.db_path)
    print(f"Wrote {n} rows to {settings.db_path}")


if __name__ == "__main__":
    main()
