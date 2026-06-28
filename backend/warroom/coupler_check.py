"""Connectivity + discovery tool for the Coupler.io MCP server.

Run this once with your COUPLER_ACCESS_TOKEN set to:
  1. verify the token + Docker MCP server work,
  2. print the available MCP tools and their argument schemas,
  3. list your data flows,
  4. preview a flow's columns + sample rows — so you can configure
     COUPLER_DATAFLOW / COUPLER_TABLE / COUPLER_COLMAP for the real schema.

Usage:
  python -m warroom.coupler_check                 # tools + dataflows
  python -m warroom.coupler_check <table_or_flow> # also preview rows from a table

Requires Docker running and `pip install "anthropic[mcp]" mcp`.
"""

from __future__ import annotations

import json
import sys

from warroom.config import Settings


def _text_blocks(result) -> str:
    out = []
    for block in getattr(result, "content", []) or []:
        t = getattr(block, "text", None)
        if t:
            out.append(t)
    return "\n".join(out)


async def _run(table: str | None) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    s = Settings.load()
    if not s.coupler_access_token:
        print("ERROR: set COUPLER_ACCESS_TOKEN in backend/.env first "
              "(get one at app.coupler.io/app/mcp/).")
        sys.exit(1)

    params = StdioServerParameters(
        command="docker",
        args=["run", "--rm", "-i", "-e", "COUPLER_ACCESS_TOKEN",
              "ghcr.io/railsware/coupler-io-mcp-server"],
        env={"COUPLER_ACCESS_TOKEN": s.coupler_access_token},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("\n=== MCP TOOLS ===")
            for t in (await session.list_tools()).tools:
                schema = getattr(t, "inputSchema", None)
                props = list((schema or {}).get("properties", {}).keys()) if \
                    isinstance(schema, dict) else []
                print(f"  • {t.name}  args={props}")

            print("\n=== DATA FLOWS ===")
            try:
                flows = await session.call_tool("list-dataflows", {})
                print(_text_blocks(flows)[:4000] or "(none)")
            except Exception as exc:
                print(f"(list-dataflows failed: {exc})")

            if table:
                print(f"\n=== PREVIEW: SELECT * FROM {table} LIMIT 5 ===")
                arg = s.coupler_query_arg
                call_args = {arg: f"SELECT * FROM {table} LIMIT 5"}
                if s.coupler_dataflow:
                    call_args["dataflow_id"] = s.coupler_dataflow
                try:
                    res = await session.call_tool("get-data", call_args)
                    body = _text_blocks(res)
                    try:
                        parsed = json.loads(body)
                        print(json.dumps(parsed, indent=2)[:4000])
                        sample = parsed[0] if isinstance(parsed, list) and parsed else None
                        if isinstance(sample, dict):
                            print("\nColumns detected:", list(sample.keys()))
                            print("Map these to canonical fields via COUPLER_COLMAP, e.g.:")
                            print('  COUPLER_COLMAP={"date":"<col>","channel":"<col>",'
                                  '"campaign":"<col>","country":"<col>","spend":"<col>",'
                                  '"conversions":"<col>","revenue":"<col>"}')
                    except json.JSONDecodeError:
                        print(body[:4000])
                except Exception as exc:
                    print(f"(get-data failed: {exc})")


def main() -> None:
    import anyio
    table = sys.argv[1] if len(sys.argv) > 1 else None
    anyio.run(_run, table)


if __name__ == "__main__":
    main()
