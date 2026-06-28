import { useEffect, useRef, useState } from "react";
import type { DashboardState, Ping } from "../types";

/** A conversion ping enriched with a client id + birth time for the globe arcs. */
export interface LivePing extends Ping {
  id: number;
  born: number;
}

const PING_TTL_MS = 4000; // arcs fade out after this long
const MAX_PINGS = 24;

export interface StreamData {
  connected: boolean;
  state: DashboardState | null;
  pings: LivePing[];
  refreshTick: number; // increments on every backend refresh -> re-pull narrative
}

/** Static render mode (?snapshot): one-shot fetch, no persistent SSE connection.
 *  Useful for demo thumbnails and headless screenshots. */
const SNAPSHOT =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).has("snapshot");

export function useWarRoomStream(): StreamData {
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<DashboardState | null>(null);
  const [pings, setPings] = useState<LivePing[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);
  const pingId = useRef(0);

  useEffect(() => {
    if (SNAPSHOT) {
      fetch("/api/state")
        .then((r) => r.json())
        .then((s: DashboardState) => {
          setState(s);
          setConnected(true);
          setRefreshTick(1);
          // Seed a few static arcs so the globe shows conversion flows in the frame.
          const now = Date.now();
          setPings(
            (s.arcs ?? []).slice(0, 8).map((a, i) => ({
              channel: a.channel,
              campaign: a.campaign,
              country: a.country,
              startLat: a.startLat,
              startLng: a.startLng,
              value: 60,
              id: i,
              born: now,
            }))
          );
        })
        .catch(() => setConnected(false));
      return;
    }

    const es = new EventSource("/api/stream");

    es.addEventListener("open", () => setConnected(true));
    es.addEventListener("error", () => setConnected(false));

    es.addEventListener("state", (e) => {
      setState(JSON.parse((e as MessageEvent).data));
    });

    es.addEventListener("refresh", () => {
      setRefreshTick((t) => t + 1);
    });

    es.addEventListener("pulse", (e) => {
      const { pings: incoming } = JSON.parse((e as MessageEvent).data) as { pings: Ping[] };
      const now = Date.now();
      const fresh: LivePing[] = incoming.map((p) => ({ ...p, id: pingId.current++, born: now }));
      setPings((prev) => [...prev, ...fresh].slice(-MAX_PINGS));
    });

    return () => es.close();
  }, []);

  // Expire old pings so arcs don't accumulate forever (live mode only).
  useEffect(() => {
    if (SNAPSHOT) return;
    const iv = setInterval(() => {
      const cutoff = Date.now() - PING_TTL_MS;
      setPings((prev) => (prev.some((p) => p.born < cutoff)
        ? prev.filter((p) => p.born >= cutoff)
        : prev));
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  return { connected, state, pings, refreshTick };
}

export const IS_SNAPSHOT = SNAPSHOT;

/** Snapshot-mode narrative: read the whole SSE briefing in one fetch (no live stream). */
export async function fetchNarrativeOnce(onText: (full: string) => void): Promise<void> {
  try {
    const res = await fetch("/api/narrative", { method: "POST" });
    const body = await res.text();
    let full = "";
    for (const line of body.split("\n")) {
      if (line.startsWith("data:")) {
        try {
          const obj = JSON.parse(line.slice(5).trim());
          if (typeof obj.text === "string") full += obj.text;
        } catch {
          /* ignore non-token data lines (e.g. done) */
        }
      }
    }
    onText(full);
  } catch {
    onText("");
  }
}

/** Stream the Claude briefing for the current state via SSE (GET). */
export function streamNarrative(
  onToken: (text: string) => void,
  onDone: () => void
): () => void {
  const es = new EventSource("/api/narrative");
  es.addEventListener("token", (e) => {
    const { text } = JSON.parse((e as MessageEvent).data);
    onToken(text);
  });
  es.addEventListener("done", () => {
    onDone();
    es.close();
  });
  es.addEventListener("error", () => {
    onDone();
    es.close();
  });
  return () => es.close();
}
