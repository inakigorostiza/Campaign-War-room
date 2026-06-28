"""Map arbitrary source rows -> the canonical `ads_daily` schema.

Real Coupler flows won't name their columns date/channel/spend/etc., so a
column map (identity by default, overridable via env) translates them. Geo
coordinates for the globe are derived from the country column.
"""

from __future__ import annotations

from warroom import geo

# canonical field -> source column name. Identity defaults: if your flow already
# uses these names, no config is needed. Override with COUPLER_COLMAP (JSON).
DEFAULT_COLMAP: dict[str, str] = {
    "date": "date",
    "channel": "channel",
    "campaign": "campaign",
    "country": "country",
    "spend": "spend",
    "impressions": "impressions",
    "clicks": "clicks",
    "conversions": "conversions",
    "revenue": "revenue",
}

CANONICAL_COLUMNS = [
    "date", "channel", "campaign", "country", "lat", "lng",
    "spend", "impressions", "clicks", "conversions", "revenue",
]


def _num(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return default


def normalize_rows(
    raw: list[dict],
    colmap: dict[str, str] | None,
    hub: tuple[float, float],
    channel_default: str = "Unknown",
) -> list[tuple]:
    """Return canonical rows as tuples in CANONICAL_COLUMNS order."""
    cm = {**DEFAULT_COLMAP, **(colmap or {})}
    out: list[tuple] = []
    for r in raw:
        date = r.get(cm["date"])
        if date is None:
            continue
        country = r.get(cm["country"])
        lat, lng = geo.coords(country, hub)
        out.append((
            str(date),
            str(r.get(cm["channel"]) or channel_default),
            str(r.get(cm["campaign"]) or "—"),
            str(country or ""),
            lat, lng,
            round(_num(r.get(cm["spend"])), 2),
            int(_num(r.get(cm["impressions"]))),
            int(_num(r.get(cm["clicks"]))),
            int(_num(r.get(cm["conversions"]))),
            round(_num(r.get(cm["revenue"])), 2),
        ))
    return out
