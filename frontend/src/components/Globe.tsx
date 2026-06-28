import { useEffect, useMemo, useRef, useState } from "react";
import GlobeGL from "react-globe.gl";
import * as THREE from "three";
import type { DashboardState } from "../types";
import { channelColor } from "../types";
import { type LivePing, IS_SNAPSHOT } from "../hooks/useWarRoomStream";

interface Props {
  state: DashboardState | null;
  pings: LivePing[];
}

export default function Globe({ state, pings }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const globeRef = useRef<any>(null);
  const [size, setSize] = useState({ w: 700, h: 700 });

  // Size the globe to its container (never let it collapse to 0).
  useEffect(() => {
    if (!wrapRef.current) return;
    const measure = () => {
      const el = wrapRef.current!;
      const w = el.clientWidth || 700;
      const h = el.clientHeight || 600;
      setSize({ w: Math.max(w, 320), h: Math.max(h, 360) });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  // One-time camera + controls setup.
  useEffect(() => {
    const g = globeRef.current;
    if (!g) return;
    const controls = g.controls();
    controls.autoRotate = !IS_SNAPSHOT; // hold still for snapshots/screenshots
    controls.autoRotateSpeed = 0.45;
    controls.enableZoom = true;
    controls.minDistance = 180;
    controls.maxDistance = 520;
    g.pointOfView({ lat: 25, lng: -20, altitude: 2.3 }, 0);
  }, []);

  // Self-contained, clearly-visible globe material (no external texture, so it
  // always draws — an unreachable texture image would leave the globe blank).
  const globeMaterial = useMemo(
    () =>
      new THREE.MeshPhongMaterial({
        color: "#1d4e89",
        emissive: "#0c2c52",
        emissiveIntensity: 0.7,
        shininess: 8,
      }),
    []
  );

  const hub = state?.hub;

  // Conversion particle arcs: each live ping -> an arc from its origin to HQ.
  const arcs = useMemo(() => {
    if (!hub) return [];
    return pings.map((p) => ({
      startLat: p.startLat,
      startLng: p.startLng,
      endLat: hub.lat,
      endLng: hub.lng,
      color: [channelColor(p.channel), "#ffffff"],
    }));
  }, [pings, hub]);

  // Campaign origin points + the HQ hub.
  const points = useMemo(() => {
    const arr =
      state?.arcs.map((a) => ({
        lat: a.startLat,
        lng: a.startLng,
        size: Math.min(0.9, 0.2 + a.conversions / 200),
        color: channelColor(a.channel),
        label: `${a.channel} · ${a.campaign} (${a.country})`,
      })) ?? [];
    if (hub) {
      arr.push({ lat: hub.lat, lng: hub.lng, size: 0.7, color: "#e8f0ff", label: hub.name });
    }
    return arr;
  }, [state, hub]);

  const rings = useMemo(() => (hub ? [{ lat: hub.lat, lng: hub.lng }] : []), [hub]);

  return (
    <div ref={wrapRef} className="globe-wrap">
      <GlobeGL
        ref={globeRef}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        globeMaterial={globeMaterial}
        showGraticules
        showAtmosphere
        atmosphereColor="#4d9bff"
        atmosphereAltitude={0.28}
        arcsData={arcs}
        arcColor={"color" as any}
        arcStroke={0.7}
        arcDashLength={0.45}
        arcDashGap={0.15}
        arcDashInitialGap={() => Math.random()}
        arcDashAnimateTime={1400}
        arcAltitudeAutoScale={0.45}
        pointsData={points}
        pointLat={"lat" as any}
        pointLng={"lng" as any}
        pointColor={"color" as any}
        pointAltitude={"size" as any}
        pointRadius={0.34}
        pointLabel={"label" as any}
        ringsData={rings}
        ringColor={() => "#6fb1ff"}
        ringMaxRadius={5}
        ringPropagationSpeed={2}
        ringRepeatPeriod={1100}
      />
    </div>
  );
}
