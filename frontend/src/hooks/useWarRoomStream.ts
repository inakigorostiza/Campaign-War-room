import { useEffect, useRef, useState } from "react";
import type { Arc, DashboardState, Ping } from "../types";

/** A conversion ping enriched with a client id + birth time for the globe arcs. */
export interface LivePing extends Ping {
  id: number;
  born: number;
}

const PING_TTL_MS = 4000; // arcs fade out after this long
const MAX_PINGS = 24;
const POLL_MS = 5000; // re-pull dashboard state on this cadence
const PULSE_MS = 1100; // emit client-side conversion pulses this often

/** Static render mode (?snapshot): one-shot fetch, no polling / pulses. */
const SNAPSHOT =
  typeof window !== "undefined" &&
  new URLSearchParams(window.location.search).has("snapshot");

export interface StreamData {
  connected: boolean;
  state: DashboardState | null;
  pings: LivePing[];
  refreshTick: number; // increments when the backend version changes -> re-pull narrative
}

/** Sample conversion pings weighted by each campaign's conversions. */
function samplePings(arcs: Arc[], pingId: { current: number }): LivePing[] {
  if (!arcs.length) return [];
  const weights = arcs.map((a) => Math.max(1, a.conversions));
  const total = weights.reduce((s, w) => s + w, 0);
  const n = 2 + Math.floor(Math.random() * 5);
  const now = Date.now();
  const out: LivePing[] = [];
  for (let i = 0; i < n; i++) {
    let r = Math.random() * total;
    let idx = 0;
    while (idx < arcs.length - 1 && (r -= weights[idx]) > 0) idx++;
    const a = arcs[idx];
    out.push({
      channel: a.channel,
      campaign: a.campaign,
      country: a.country,
      startLat: a.startLat,
      startLng: a.startLng,
      value: Math.round(45 + Math.random() * 45),
      id: pingId.current++,
      born: now,
    });
  }
  return out;
}

export function useWarRoomStream(): StreamData {
  const [connected, setConnected] = useState(false);
  const [state, setState] = useState<DashboardState | null>(null);
  const [pings, setPings] = useState<LivePing[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);
  const pingId = useRef(0);
  const lastVersion = useRef<number | null>(null);
  const stateRef = useRef<DashboardState | null>(null);

  // Fetch + poll dashboard state.
  useEffect(() => {
    let alive = true;

    const pull = async () => {
      try {
        const res = await fetch("/api/state", { cache: "no-store" });
        const s: DashboardState = await res.json();
        if (!alive) return;
        setConnected(true);
        setState(s);
        stateRef.current = s;
        if (lastVersion.current === null) {
          lastVersion.current = s.version;
          setRefreshTick((t) => t + 1); // first load -> pull narrative
        } else if (s.version !== lastVersion.current) {
          lastVersion.current = s.version;
          setRefreshTick((t) => t + 1);
        }
      } catch {
        if (alive) setConnected(false);
      }
    };

    pull();
    if (SNAPSHOT) {
      // Seed a few static arcs so the globe shows flows in the frame, then stop.
      const seed = setTimeout(() => {
        const s = stateRef.current;
        if (!s) return;
        const now = Date.now();
        setPings(
          (s.arcs ?? []).slice(0, 8).map((a, i) => ({
            channel: a.channel, campaign: a.campaign, country: a.country,
            startLat: a.startLat, startLng: a.startLng, value: 60, id: i, born: now,
          }))
        );
      }, 400);
      return () => {
        alive = false;
        clearTimeout(seed);
      };
    }

    const poll = setInterval(pull, POLL_MS);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, []);

  // Client-side conversion pulses (live mode only).
  useEffect(() => {
    if (SNAPSHOT) return;
    const iv = setInterval(() => {
      const s = stateRef.current;
      if (!s?.arcs?.length) return;
      const fresh = samplePings(s.arcs, pingId);
      const cutoff = Date.now() - PING_TTL_MS;
      setPings((prev) => [...prev.filter((p) => p.born >= cutoff), ...fresh].slice(-MAX_PINGS));
    }, PULSE_MS);
    return () => clearInterval(iv);
  }, []);

  return { connected, state, pings, refreshTick };
}

export const IS_SNAPSHOT = SNAPSHOT;

/** Read the whole SSE-formatted briefing in one fetch (works against Flask + Vercel). */
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
