"""Claude-generated war-room briefing from computed anomaly facts.

Default mode is facts -> phrasing: the deterministic anomaly engine computes the
numbers, Claude turns them into a tight analyst briefing. Streaming so the
frontend's narrative panel renders token by token. Model + SDK usage follow the
current `claude-api` guidance (Anthropic Python SDK, model `claude-opus-4-8`,
adaptive thinking).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from warroom.config import Settings

SYSTEM_PROMPT = (
    "You are the lead analyst in a real-time marketing war room. You receive "
    "pre-computed anomaly facts (already verified — do not recompute or doubt the "
    "numbers). Write a punchy situational briefing for a CMO watching a live "
    "dashboard.\n\n"
    "Rules:\n"
    "- Lead with the single most important movement in one sentence.\n"
    "- Name the channel, campaign, metric, and exact % change.\n"
    "- Offer one plausible cause and one concrete next action per critical item.\n"
    "- Be concise: 3-5 short sentences total, no preamble, no bullet headers like "
    "'Summary:'. Plain text. Confident, calm, control-room tone.\n"
    "- If there are no anomalies, say the channels are stable and give the headline KPI."
)


def _facts_payload(state: dict) -> str:
    return json.dumps({
        "date": state.get("latest_date"),
        "kpis": state.get("kpis", {}),
        "anomalies": state.get("anomalies", []),
        "channels": state.get("channels", []),
    }, indent=2)


def _fallback_briefing(state: dict) -> str:
    """Deterministic text when no Anthropic key is configured (keeps the demo alive)."""
    anomalies = state.get("anomalies", [])
    kpis = state.get("kpis", {})
    if not anomalies:
        return (
            f"All channels stable for {state.get('latest_date')}. "
            f"Spend ${kpis.get('spend', 0):,.0f}, {kpis.get('conversions', 0)} conversions, "
            f"blended CPA ${kpis.get('cpa', 0):,.2f}, ROAS {kpis.get('roas', 0):.2f}x."
        )
    top = anomalies[0]
    arrow = "spiked" if top["direction"] == "up" else "dropped"
    return (
        f"{top['channel']} {arrow} on {top['campaign']}: CPA {arrow} "
        f"{top['delta_pct']:+.0f}% to ${top['today_value']:.2f} (baseline ${top['baseline_value']:.2f}, "
        f"z={top['zscore']}). Likely an auction-cost shift in {top['country']}; "
        f"review bids and creative on this campaign. "
        f"Blended CPA ${kpis.get('cpa', 0):,.2f}, ROAS {kpis.get('roas', 0):.2f}x across all channels."
    )


def stream_briefing(settings: Settings, state: dict) -> Iterator[str]:
    """Yield the briefing as text chunks. Falls back to deterministic text without a key."""
    if not settings.has_anthropic:
        yield _fallback_briefing(state)
        return

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_msg = (
        "Here are the verified anomaly facts and KPIs from the live dashboard. "
        "Write the war-room briefing.\n\n" + _facts_payload(state)
    )
    try:
        with client.messages.stream(
            model=settings.claude_model,
            max_tokens=600,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as exc:  # never let a transient API error blank the panel
        yield _fallback_briefing(state)
        yield f"\n\n(Live narrative unavailable: {exc})"


def briefing_text(settings: Settings, state: dict) -> str:
    return "".join(stream_briefing(settings, state))
