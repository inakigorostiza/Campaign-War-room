import { useEffect, useRef, useState } from "react";
import Globe from "./components/Globe";
import ErrorBoundary from "./components/ErrorBoundary";
import KpiRail from "./components/KpiRail";
import AnomalyCards from "./components/AnomalyCards";
import NarrativePanel from "./components/NarrativePanel";
import {
  useWarRoomStream,
  streamNarrative,
  fetchNarrativeOnce,
  IS_SNAPSHOT,
} from "./hooks/useWarRoomStream";

export default function App() {
  const { connected, state, pings, refreshTick } = useWarRoomStream();
  const [narrative, setNarrative] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [flash, setFlash] = useState(false);
  const startedOnce = useRef(false);

  // Pull the Claude briefing on first state and on every backend refresh.
  const haveState = !!state;
  useEffect(() => {
    if (!haveState) return;
    if (!startedOnce.current) startedOnce.current = true;

    setNarrative("");
    setStreaming(true);
    if (IS_SNAPSHOT) {
      fetchNarrativeOnce((full) => {
        setNarrative(full);
        setStreaming(false);
      });
      return;
    }
    const stop = streamNarrative(
      (t) => setNarrative((prev) => prev + t),
      () => setStreaming(false)
    );
    return stop;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [haveState, refreshTick]);

  // Brief screen flash when fresh data lands.
  useEffect(() => {
    if (refreshTick === 0) return;
    setFlash(true);
    const t = setTimeout(() => setFlash(false), 700);
    return () => clearTimeout(t);
  }, [refreshTick]);

  const sourceLabel = state?.source === "coupler" ? "Coupler.io · live" : "Coupler.io · seed";

  return (
    <div className={`app ${flash ? "flash" : ""}`}>
      <div className="bg-grid" />

      <header className="topbar">
        <div className="brand">
          <span className="brand-glyph" />
          <span className="brand-name">WAR ROOM</span>
          <span className="brand-sub">marketing mission control</span>
        </div>
        <div className="status">
          <span className={`pill ${connected ? "ok" : "bad"}`}>
            <span className="pill-dot" />
            {connected ? "LIVE" : "RECONNECTING"}
          </span>
          <span className="pill muted">{sourceLabel}</span>
          <span className="pill muted">refresh #{state?.version ?? 0}</span>
        </div>
      </header>

      <main className="grid">
        <aside className="col-left">
          <KpiRail state={state} />
          <NarrativePanel
            text={narrative}
            streaming={streaming}
            date={state?.latest_date ?? null}
          />
        </aside>

        <section className="col-center">
          <ErrorBoundary
            fallback={
              <div className="globe-fallback">
                <div className="globe-fallback-ring" />
                <span>3D globe unavailable (no WebGL in this view)</span>
              </div>
            }
          >
            <Globe state={state} pings={pings} />
          </ErrorBoundary>
          <div className="globe-caption">
            Conversions flowing to HQ · {pings.length} live signals
          </div>
        </section>

        <aside className="col-right">
          <AnomalyCards anomalies={state?.anomalies ?? []} />
        </aside>
      </main>
    </div>
  );
}
