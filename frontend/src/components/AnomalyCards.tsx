import { useEffect, useRef } from "react";
import gsap from "gsap";
import type { Anomaly } from "../types";
import { channelColor } from "../types";

interface Props {
  anomalies: Anomaly[];
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: "#ff3b5c",
  warning: "#ffb020",
  info: "#38bdf8",
};

export default function AnomalyCards({ anomalies }: Props) {
  const listRef = useRef<HTMLDivElement>(null);

  // "Breathing" pulse on critical/warning cards via a looping GSAP timeline.
  useEffect(() => {
    if (!listRef.current) return;
    const cards = Array.from(
      listRef.current.querySelectorAll<HTMLElement>(".anomaly-card.alive")
    );
    if (cards.length === 0) return;
    const tweens = cards.map((card, i) => {
      const dur = card.dataset.severity === "critical" ? 1.1 : 1.8;
      return gsap.to(card, {
        boxShadow: `0 0 26px ${card.dataset.glow}`,
        borderColor: card.dataset.glow,
        repeat: -1,
        yoyo: true,
        duration: dur,
        delay: i * 0.15,
        ease: "sine.inOut",
      });
    });
    // Snap-in entrance.
    gsap.fromTo(
      cards,
      { y: 14, opacity: 0 },
      { y: 0, opacity: 1, duration: 0.5, stagger: 0.08, ease: "power2.out" }
    );
    return () => tweens.forEach((t) => t.kill());
  }, [anomalies]);

  return (
    <div className="panel anomaly-panel">
      <div className="panel-title">
        Anomalies
        {anomalies.length > 0 && <span className="badge">{anomalies.length}</span>}
      </div>
      <div className="anomaly-list" ref={listRef}>
        {anomalies.length === 0 && (
          <div className="anomaly-empty">All channels nominal.</div>
        )}
        {anomalies.map((a, i) => {
          const glow = SEVERITY_COLOR[a.severity];
          const alive = a.severity !== "info";
          const arrow = a.direction === "up" ? "▲" : "▼";
          return (
            <div
              key={`${a.channel}-${a.campaign}-${i}`}
              className={`anomaly-card ${alive ? "alive" : ""}`}
              data-severity={a.severity}
              data-glow={glow}
              style={{ borderColor: "rgba(255,255,255,0.08)" }}
            >
              <div className="anomaly-head">
                <span className="anomaly-dot" style={{ background: channelColor(a.channel) }} />
                <span className="anomaly-title">
                  {a.channel} · {a.campaign}
                </span>
                <span className="anomaly-delta" style={{ color: glow }}>
                  {arrow} {a.delta_pct > 0 ? "+" : ""}
                  {a.delta_pct.toFixed(0)}%
                </span>
              </div>
              <div className="anomaly-sub">
                CPA ${a.today_value.toFixed(2)} vs ${a.baseline_value.toFixed(2)} baseline · z={a.zscore} · {a.country}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
