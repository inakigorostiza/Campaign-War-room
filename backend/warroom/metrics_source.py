"""Metrics data sources — the seam between local seed data and live Coupler.io.

Both sources honor the same contract: `query(sql) -> list[dict]` over a table
named `ads_daily`. Coupler's MCP `get-data` tool executes read-only SQL against a
SQLite snapshot of a data flow, so a local SQLite with the same schema is a
drop-in stand-in. Downstream code never knows which source it is talking to.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path

from warroom.config import Settings


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
            cur = conn.execute(sql)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


class CouplerMCPSource(MetricsSource):
    """Live source: runs SQL through the Coupler.io MCP server's `get-data` tool.

    The server is launched on demand over stdio (Docker image
    ghcr.io/railsware/coupler-io-mcp-server) and authenticated with a Personal
    Access Token. `get-data` returns rows from a read-only SQLite snapshot of the
    selected data flow — the same shape SeedSQLiteSource produces.

    NOTE: requires a configured Coupler data flow whose dataset exposes an
    `ads_daily`-shaped table; set COUPLER_DATAFLOW_ID / COUPLER_DATASET to match
    your account. This path is behind WARROOM_SOURCE=coupler and is not exercised
    in the seeded demo.
    """

    def __init__(self, access_token: str, dataflow_id: str | None = None):
        self.access_token = access_token
        self.dataflow_id = dataflow_id

    def query(self, sql: str) -> list[dict]:
        # Lazy imports so the seeded demo never needs the mcp client installed.
        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def _run() -> list[dict]:
            params = StdioServerParameters(
                command="docker",
                args=[
                    "run", "--rm", "-i",
                    "-e", "COUPLER_ACCESS_TOKEN",
                    "ghcr.io/railsware/coupler-io-mcp-server",
                ],
                env={"COUPLER_ACCESS_TOKEN": self.access_token},
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tool_args: dict = {"query": sql}
                    if self.dataflow_id:
                        tool_args["dataflow_id"] = self.dataflow_id
                    result = await session.call_tool("get-data", tool_args)
                    return _parse_mcp_rows(result)

        return anyio.run(_run)


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
            # Coupler may wrap rows under a key like "rows" / "data".
            for key in ("rows", "data", "results"):
                if isinstance(payload.get(key), list):
                    rows.extend(r for r in payload[key] if isinstance(r, dict))
                    break
    return rows


def build_source(settings: Settings) -> MetricsSource:
    if settings.source == "coupler":
        if not settings.coupler_access_token:
            raise ValueError("WARROOM_SOURCE=coupler requires COUPLER_ACCESS_TOKEN.")
        return CouplerMCPSource(settings.coupler_access_token)
    return SeedSQLiteSource(settings.db_path)
