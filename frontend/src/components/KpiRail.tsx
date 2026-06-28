import type { DashboardState } from "../types";
import { channelColor } from "../types";

interface Props {
  state: DashboardState | null;
}

function fmtMoney(n: number): string {
  return "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export default function KpiRail({ state }: Props) {
  const k = state?.kpis;
  const tiles = [
    { label: "Spend", value: k ? fmtMoney(k.spend) : "—" },
    { label: "Conversions", value: k ? k.conversions.toLocaleString() : "—" },
    { label: "Blended CPA", value: k ? "$" + k.cpa.toFixed(2) : "—" },
    { label: "ROAS", value: k ? k.roas.toFixed(2) + "x" : "—" },
  ];

  return (
    <div className="panel kpi-panel">
      <div className="panel-title">Live KPIs</div>
      <div className="kpi-grid">
        {tiles.map((t) => (
          <div className="kpi-tile" key={t.label}>
            <div className="kpi-value">{t.value}</div>
            <div className="kpi-label">{t.label}</div>
          </div>
        ))}
      </div>

      <div className="panel-title" style={{ marginTop: 18 }}>Channels</div>
      <div className="channel-list">
        {state?.channels.map((c) => (
          <div className="channel-row" key={c.channel}>
            <span className="channel-dot" style={{ background: channelColor(c.channel) }} />
            <span className="channel-name">{c.channel}</span>
            <span className="channel-spend">{fmtMoney(c.spend)}</span>
            <span className="channel-cpa">CPA ${c.cpa.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
