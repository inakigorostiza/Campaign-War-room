export interface Kpis {
  spend: number;
  conversions: number;
  revenue: number;
  cpa: number;
  roas: number;
  ctr: number;
}

export interface ChannelRollup {
  channel: string;
  spend: number;
  conversions: number;
  cpa: number;
}

export interface Arc {
  channel: string;
  campaign: string;
  country: string;
  startLat: number;
  startLng: number;
  conversions: number;
  spend: number;
}

export interface Anomaly {
  channel: string;
  campaign: string;
  country: string;
  metric: string;
  direction: "up" | "down";
  today_value: number;
  baseline_value: number;
  delta_pct: number;
  zscore: number;
  severity: "critical" | "warning" | "info";
  spend: number;
  conversions: number;
}

export interface Hub {
  name: string;
  lat: number;
  lng: number;
}

export interface DashboardState {
  latest_date: string | null;
  kpis: Kpis;
  channels: ChannelRollup[];
  arcs: Arc[];
  anomalies: Anomaly[];
  hub: Hub;
  version: number;
  source: string;
  refresh_reason?: string;
}

export interface Ping {
  channel: string;
  campaign: string;
  country: string;
  startLat: number;
  startLng: number;
  value: number;
}

export const CHANNEL_COLORS: Record<string, string> = {
  Meta: "#1da1ff",
  Google: "#ffd166",
  TikTok: "#ff4d8d",
};

export function channelColor(channel: string): string {
  return CHANNEL_COLORS[channel] ?? "#7c8db5";
}
