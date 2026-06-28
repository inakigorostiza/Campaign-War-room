"""Country -> (lat, lng) centroid lookup for placing conversion arcs on the globe.

Real ad data carries a country (ISO-2, ISO-3, or name) but no coordinates, so we
map it to an approximate centroid. Unknown countries fall back to the hub so an
arc still renders rather than disappearing.
"""

from __future__ import annotations

# Approximate centroids for common ad markets. Extend as needed.
_CENTROIDS: dict[str, tuple[float, float]] = {
    "US": (39.83, -98.58), "CA": (56.13, -106.35), "MX": (23.63, -102.55),
    "BR": (-14.24, -51.93), "AR": (-38.42, -63.62),
    "GB": (54.0, -2.0), "IE": (53.41, -8.24), "FR": (46.6, 2.21),
    "DE": (51.17, 10.45), "ES": (40.46, -3.75), "PT": (39.4, -8.22),
    "IT": (41.87, 12.57), "NL": (52.13, 5.29), "BE": (50.5, 4.47),
    "CH": (46.82, 8.23), "AT": (47.52, 14.55), "SE": (60.13, 18.64),
    "NO": (60.47, 8.47), "DK": (56.26, 9.5), "FI": (61.92, 25.75),
    "PL": (51.92, 19.15), "CZ": (49.82, 15.47), "RO": (45.94, 24.97),
    "GR": (39.07, 21.82), "TR": (38.96, 35.24), "RU": (61.52, 105.32),
    "UA": (48.38, 31.17),
    "AE": (23.42, 53.85), "SA": (23.89, 45.08), "IL": (31.05, 34.85),
    "ZA": (-30.56, 22.94), "NG": (9.08, 8.68), "EG": (26.82, 30.8),
    "IN": (20.59, 78.96), "PK": (30.38, 69.35), "CN": (35.86, 104.2),
    "JP": (36.2, 138.25), "KR": (35.91, 127.77), "ID": (-0.79, 113.92),
    "SG": (1.35, 103.82), "MY": (4.21, 101.98), "TH": (15.87, 100.99),
    "VN": (14.06, 108.28), "PH": (12.88, 121.77),
    "AU": (-25.27, 133.78), "NZ": (-40.9, 174.89),
}

# Common name -> ISO-2 (lowercased keys), for sources that emit country names.
_NAME_TO_ISO: dict[str, str] = {
    "united states": "US", "usa": "US", "united states of america": "US",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB", "england": "GB",
    "germany": "DE", "france": "FR", "spain": "ES", "portugal": "PT",
    "italy": "IT", "netherlands": "NL", "belgium": "BE", "ireland": "IE",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "argentina": "AR",
    "australia": "AU", "new zealand": "NZ", "japan": "JP", "south korea": "KR",
    "india": "IN", "china": "CN", "singapore": "SG", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "poland": "PL",
    "switzerland": "CH", "austria": "AT", "united arab emirates": "AE",
    "saudi arabia": "SA", "south africa": "ZA", "turkey": "TR",
}

# Minimal ISO-3 -> ISO-2 for the markets above.
_ISO3_TO_ISO2: dict[str, str] = {
    "USA": "US", "GBR": "GB", "DEU": "DE", "FRA": "FR", "ESP": "ES",
    "PRT": "PT", "ITA": "IT", "NLD": "NL", "BEL": "BE", "IRL": "IE",
    "CAN": "CA", "MEX": "MX", "BRA": "BR", "ARG": "AR", "AUS": "AU",
    "NZL": "NZ", "JPN": "JP", "KOR": "KR", "IND": "IN", "CHN": "CN",
    "SGP": "SG", "SWE": "SE", "NOR": "NO", "DNK": "DK", "FIN": "FI",
    "POL": "PL", "CHE": "CH", "AUT": "AT", "ARE": "AE", "SAU": "SA",
    "ZAF": "ZA", "TUR": "TR",
}


def to_iso2(value: str | None) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    if len(v) == 2 and v.upper() in _CENTROIDS:
        return v.upper()
    if len(v) == 3 and v.upper() in _ISO3_TO_ISO2:
        return _ISO3_TO_ISO2[v.upper()]
    return _NAME_TO_ISO.get(v.lower())


def coords(country: str | None, fallback: tuple[float, float]) -> tuple[float, float]:
    """Return (lat, lng) for a country, or `fallback` (typically the hub) if unknown."""
    iso = to_iso2(country)
    if iso and iso in _CENTROIDS:
        return _CENTROIDS[iso]
    return fallback
