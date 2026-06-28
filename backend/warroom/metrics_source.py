"""Metrics data sources — the seam between local seed data and live Coupler.io.

Both sources honor the same contract: `query(sql) -> list[dict]` over a table
named `ads_daily`. The seed reads a local SQLite file. The Coupler source pulls
real rows from the Coupler.io MCP server, normalizes them to the canonical
`ads_daily` schema, materializes them in an in-memory SQLite, and runs the
downstream SQL against that — so anomalies/state/narrative code is identical for
demo and live data.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path

from warroom.config import Settings
from warroom.normalize import CANONICAL_COLUMNS, normalize_rows
from warroom.seed import HUB


class MetricsSource(ABC):
    @abstractmethod
    def query(self, sql: str) -> list[dict]:
        """Run a read-only SQL query against `ads_daily` and return rows as dicts."""

    def close(self) -> None:  # pragma: no cover - optional override
        pass


class SeedSQLiteSource(MetricsSource):
    """Reads from the local seed SQLite snapshot (hybrid demo mode)."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Seed DB not found at {self.db_path}. Run `python -m warroom.seed` first."
            )

    def query(self, sql: str) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql).fetchall()]
        finally:
            conn.close()


class CouplerMCPSource(MetricsSource):
    """Live source backed by the Coupler.io MCP server.

    Pulls `SELECT * FROM <table>` from the flow's snapshot via the MCP `get-data`
    tool, normalizes to canonical `ads_daily`, and caches it in memory for
    `refresh_seconds` so each dashboard refresh hits the MCP server at most once.
    """

    def __init__(self, settings: Settings):
        self.s = settings
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._fetched_at = 0.0

    # -- public contract -----------------------------------------------------
    def query(self, sql: str) -> list[dict]:
        with self._lock:
            self._ensure_fresh()
            self._conn.row_factory = sqlite3.Row
            return [dict(r) for r in self._conn.execute(sql).fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- internals -----------------------------------------------------------
    def _ensure_fresh(self) -> None:
        ttl = max(5, self.s.refresh_seconds)
        if self._conn is not None and (time.monotonic() - self._fetched_at) < ttl:
            return
        raw = self._pull_raw()
        rows = normalize_rows(
            raw, self.s.coupler_colmap, (HUB["lat"], HUB["lng"]),
            channel_default=self.s.coupler_channel_default,
        )
        self._materialize(rows)
        self._fetched_at = time.monotonic()

    def _materialize(self, rows: list[tuple]) -> None:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        cols = ", ".join(CANONICAL_COLUMNS)
        placeholders = ",".join("?" * len(CANONICAL_COLUMNS))
        conn.execute(f"CREATE TABLE ads_daily ({cols})")
        conn.executemany(f"INSERT INTO ads_daily ({cols}) VALUES ({placeholders})", rows)
        conn.commit()
        if self._conn:
            self._conn.close()
        self._conn = conn

    def _pull_raw(self) -> list[dict]:
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        token = self.s.coupler_access_token
        sql = f"SELECT * FROM {self.s.coupler_table}"

        async def _run() -> list[dict]:
            params = StdioServerParameters(
                command="docker",
                args=["run", "--rm", "-i", "-e", "COUPLER_ACCESS_TOKEN",
                      "ghcr.io/railsware/coupler-io-mcp-server"],
                env={"COUPLER_ACCESS_TOKEN": token},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tool_name, args = await self._build_call(session, sql)
                    result = await session.call_tool(tool_name, args)
                    return _parse_mcp_rows(result)

        return anyio.run(_run)

    async def _build_call(self, session, sql: str):
        """Introspect the MCP tools to find get-data and its SQL/dataflow args."""
        tools = (await session.list_tools()).tools
        gd = next((t for t in tools if t.name == "get-data"), None)
        if gd is None:
            gd = next((t for t in tools
                       if "data" in t.name.lower() and "get" in t.name.lower()), None)
        if gd is None:
            raise RuntimeError(
                "Coupler MCP exposed no get-data tool. Run "
                "`python -m warroom.coupler_check` to inspect available tools."
            )
        props = (getattr(gd, "inputSchema", None) or {}).get("properties", {}) if \
            isinstance(getattr(gd, "inputSchema", None), dict) else {}

        # Pick the SQL argument: configured name, else a query/sql-looking prop.
        sql_arg = self.s.coupler_query_arg
        if props and sql_arg not in props:
            sql_arg = next((k for k in props if k.lower() in ("query", "sql", "statement")),
                           sql_arg)
        args: dict = {sql_arg: sql}

        # Attach the dataflow id under whatever key the schema expects.
        if self.s.coupler_dataflow:
            df_key = next((k for k in props
                           if "dataflow" in k.lower() or "data_flow" in k.lower()
                           or k.lower() in ("flow", "flow_id")), None)
            args[df_key or "dataflow_id"] = self.s.coupler_dataflow
        return gd.name, args


def _parse_mcp_rows(result) -> list[dict]:
    """Extract row dicts from an MCP CallToolResult (text content carrying JSON)."""
    rows: list[dict] = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, list):
            rows.extend(r for r in payload if isinstance(r, dict))
        elif isinstance(payload, dict):
            for key in ("rows", "data", "results", "records"):
                if isinstance(payload.get(key), list):
                    rows.extend(r for r in payload[key] if isinstance(r, dict))
                    break
    return rows


def build_source(settings: Settings) -> MetricsSource:
    if settings.source == "coupler":
        if not settings.coupler_access_token:
            raise ValueError("WARROOM_SOURCE=coupler requires COUPLER_ACCESS_TOKEN.")
        return CouplerMCPSource(settings)
    return SeedSQLiteSource(settings.db_path)
