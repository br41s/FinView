import { useMemo } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
  Line,
} from "react-simple-maps";
import { anchorForSignal, type GeoSignal } from "@/lib/geo";

const WORLD_TOPO =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

const COLORS = {
  bullish: "#6B7A3A",
  bearish: "#9B3D2C",
  neutral: "#9A6B1F",
};

function markerRadius(importance: number) {
  const t = Math.max(0, Math.min(100, importance)) / 100;
  return 6 + t * 10; // 6–16
}

type Props = {
  signals?: GeoSignal[];
  onSelectSignal?: (s: GeoSignal) => void;
  selectedId?: string | null;
  hoveredId?: string | null;
  onHoverSignal?: (id: string | null) => void;
};

export function GeoMap({
  signals = [],
  onSelectSignal,
  selectedId = null,
  hoveredId = null,
  onHoverSignal,
}: Props) {
  const setHoverId = (id: string | null) => onHoverSignal?.(id);
  const hoverId = hoveredId;

  const arcs = useMemo(
    () =>
      signals
        .filter((s) => s.tickers.length > 0 && s.status === "active")
        .map((s) => ({ s, anchor: anchorForSignal(s) })),
    [signals],
  );

  return (
    <div className="relative h-full w-full overflow-hidden">
      <style>{`
        @keyframes geoPulse {
          0%, 100% { transform: scale(1); opacity: 0.95; }
          50% { transform: scale(1.35); opacity: 0.35; }
        }
        .geo-pulse { transform-box: fill-box; transform-origin: center; animation: geoPulse 2s cubic-bezier(0.2,0.8,0.2,1) infinite; }
      `}</style>
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 165 }}
        width={980}
        height={520}
        style={{ width: "100%", height: "100%" }}
      >
        <ZoomableGroup center={[10, 15]} zoom={1} minZoom={1} maxZoom={6}>
          <Geographies geography={WORLD_TOPO}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  style={{
                    default: {
                      fill: "#EDE8DE",
                      stroke: "rgba(31,27,22,0.18)",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                    hover: {
                      fill: "#E6E0D2",
                      stroke: "rgba(31,27,22,0.25)",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                    pressed: {
                      fill: "#E6E0D2",
                      stroke: "rgba(31,27,22,0.25)",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                  }}
                />
              ))
            }
          </Geographies>

          {arcs.map(({ s, anchor }) => (
            <Line
              key={`arc-${s.id}`}
              from={[s.lng, s.lat]}
              to={[anchor.lng, anchor.lat]}
              stroke="#9A6B1F"
              strokeWidth={0.6}
              strokeOpacity={0.35}
              strokeLinecap="round"
              fill="none"
            />
          ))}

          {Object.values(
            arcs.reduce<Record<string, { lng: number; lat: number; label: string }>>(
              (acc, a) => {
                acc[a.anchor.label] = a.anchor;
                return acc;
              },
              {},
            ),
          ).map((a) => (
            <Marker key={`anchor-${a.label}`} coordinates={[a.lng, a.lat]}>
              <circle r={2.5} fill="#1F1B16" opacity={0.55} />
            </Marker>
          ))}

          {signals.map((s) => {
            const r = markerRadius(s.importance);
            const color = COLORS[s.direction];
            const isActive = s.status === "active";
            const isSelected = selectedId === s.id;
            const isHovered = hoverId === s.id;
            const emphasized = isSelected || isHovered;
            return (
              <Marker
                key={s.id}
                coordinates={[s.lng, s.lat]}
                onMouseEnter={() => setHoverId(s.id)}
                onMouseLeave={() => setHoverId(null)}
                onClick={() => onSelectSignal?.(s)}
                style={{ default: { cursor: "pointer" } }}
              >
                {isActive && (
                  <circle
                    r={r}
                    fill={color}
                    fillOpacity={0.25}
                    className="geo-pulse"
                  />
                )}
                {isSelected && (
                  <circle
                    r={r + 4}
                    fill="none"
                    stroke="#9A6B1F"
                    strokeWidth={1.2}
                    strokeOpacity={0.9}
                  />
                )}
                <circle
                  r={emphasized ? r * 0.8 : r * 0.55}
                  fill={color}
                  fillOpacity={0.9}
                  stroke="#FEFCF5"
                  strokeWidth={emphasized ? 1.4 : 1}
                />
                {hoverId === s.id && (
                  <g transform={`translate(${r + 6}, -${r})`}>
                    <rect
                      x={0}
                      y={0}
                      rx={4}
                      ry={4}
                      width={Math.max(120, s.headline.length * 4.8)}
                      height={32}
                      fill="#FEFCF5"
                      stroke="rgba(31,27,22,0.14)"
                    />
                    <text
                      x={8}
                      y={13}
                      fontSize={7}
                      fill="#1F1B16"
                      style={{ fontFamily: "Geist, system-ui, sans-serif", fontWeight: 600 }}
                    >
                      {s.headline}
                    </text>
                    <text
                      x={8}
                      y={25}
                      fontSize={6}
                      fill="rgba(31,27,22,0.6)"
                      style={{ fontFamily: "JetBrains Mono, monospace" }}
                    >
                      {s.location} · risk {s.riskScore.toFixed(1)}
                    </text>
                  </g>
                )}
              </Marker>
            );
          })}
        </ZoomableGroup>
      </ComposableMap>

      <div className="pointer-events-none absolute bottom-4 left-4 flex items-center gap-4 rounded-md border border-[rgba(31,27,22,0.14)] bg-[#FEFCF5]/85 px-3 py-2 text-[11px] text-[#1F1B16] shadow-[0_4px_16px_rgba(31,27,22,0.08)] backdrop-blur">
        <LegendDot color={COLORS.bearish} label="Bearish" />
        <LegendDot color={COLORS.bullish} label="Bullish" />
        <LegendDot color={COLORS.neutral} label="Neutral" />
        <span className="ml-2 font-mono text-[10px] text-[rgba(31,27,22,0.6)]">
          size = importance
        </span>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="inline-block h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: color }}
      />
      <span>{label}</span>
    </span>
  );
}