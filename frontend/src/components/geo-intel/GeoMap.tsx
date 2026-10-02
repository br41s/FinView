import { useMemo, useState } from "react";
import {
  ComposableMap,
  Geographies,
  Geography,
  Marker,
  ZoomableGroup,
  Line,
} from "react-simple-maps";
import { anchorForSignal, type GeoSignal } from "@/lib/geo";

// Two base resolutions: coarse 110m by default (tiny, fast first paint), crisp
// 50m once zoomed in so country outlines don't look faceted. On top of that, at
// detail zoom we overlay admin-1 (states/provinces) so acercar reveals *regions*,
// not just a scaled-up version of the same country lines. Natural Earth data
// (public domain) via the same jsdelivr CDN the base map already uses.
const WORLD_TOPO_110 =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
const WORLD_TOPO_50 =
  "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json";
const ADMIN1_TOPO =
  "https://cdn.jsdelivr.net/gh/martynafford/natural-earth-geojson@master/50m/cultural/ne_50m_admin_1_states_provinces.json";

const COLORS = {
  bullish: "var(--fv-success)",
  bearish: "var(--fv-danger)",
  neutral: "var(--fv-ochre)",
};

const DEFAULT_CENTER: [number, number] = [10, 15];
const DEFAULT_ZOOM = 1;
const SELECTED_ZOOM = 4;
// Above this zoom, swap the base to 50m and lazy-mount the admin-1 region layer.
const DETAIL_ZOOM = 2.5;

function markerRadius(importance: number) {
  const t = Math.max(0, Math.min(100, importance)) / 100;
  return 6 + t * 10; // 6–16
}

type View = { center: [number, number]; zoom: number };

// Where the map flies for a selection: onto the signal, or back to the default
// view when nothing (or nothing visible) is selected.
function flyTarget(selectedId: string | null, signals: GeoSignal[]): View {
  const target = selectedId ? signals.find((s) => s.id === selectedId) : null;
  return target
    ? { center: [target.lng, target.lat], zoom: SELECTED_ZOOM }
    : { center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM };
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

  // The view is state, not derived from the selection, because the user can
  // also pan/zoom it (onMoveEnd below).
  const [view, setView] = useState<View>(() => flyTarget(selectedId, signals));
  const { center, zoom } = view;
  // Only the programmatic fly-to (selection) should ease over 900ms; a live
  // wheel/drag gesture must track the cursor 1:1, so we disable the transition
  // the moment the user starts moving the map.
  const [animate, setAnimate] = useState(true);

  // Fly to the selected signal; return to the default view on deselect. Driven
  // entirely by selectedId so map-marker clicks and Live Feed clicks (which set
  // the same `selected` state upstream) both trigger the same zoom. `signals`
  // identity is part of the trigger on purpose: every poll hands down a new
  // array and re-centres the view, as it always has.
  //
  // Adjusted during render rather than in an effect: React re-runs the render
  // with the new state before committing, so the flown-to view is what paints.
  const [flownTo, setFlownTo] = useState({ selectedId, signals });
  if (flownTo.selectedId !== selectedId || flownTo.signals !== signals) {
    setFlownTo({ selectedId, signals });
    setAnimate(true);
    setView(flyTarget(selectedId, signals));
  }

  const detail = zoom >= DETAIL_ZOOM;

  const arcs = useMemo(
    () =>
      signals
        .filter((s) => s.tickers.length > 0 && s.status === "active")
        .map((s) => ({ s, anchor: anchorForSignal(s) })),
    [signals],
  );

  return (
    <div className={`relative h-full w-full overflow-hidden ${animate ? "geo-animate" : ""}`}>
      <style>{`
        @keyframes geoPulse {
          0%, 100% { transform: scale(1); opacity: 0.95; }
          50% { transform: scale(1.35); opacity: 0.35; }
        }
        .geo-pulse { transform-box: fill-box; transform-origin: center; animation: geoPulse 2s cubic-bezier(0.2,0.8,0.2,1) infinite; }
        .geo-animate .rsm-zoomable-group { transition: transform 900ms cubic-bezier(0.16, 1, 0.3, 1); }
      `}</style>
      <ComposableMap
        projection="geoEqualEarth"
        projectionConfig={{ scale: 165 }}
        width={980}
        height={520}
        style={{ width: "100%", height: "100%" }}
      >
        <ZoomableGroup
          center={center}
          zoom={zoom}
          minZoom={1}
          maxZoom={6}
          onMoveStart={() => setAnimate(false)}
          onMoveEnd={({ coordinates, zoom: z }) => {
            setView({ center: coordinates, zoom: z });
          }}
        >
          <Geographies geography={detail ? WORLD_TOPO_50 : WORLD_TOPO_110}>
            {({ geographies }) =>
              geographies.map((geo) => (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  style={{
                    default: {
                      fill: "var(--muted)",
                      stroke: "color-mix(in srgb, var(--fv-ink) 18%, transparent)",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                    hover: {
                      fill: "color-mix(in srgb, var(--muted), var(--fv-ink) 4%)",
                      stroke: "color-mix(in srgb, var(--fv-ink) 25%, transparent)",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                    pressed: {
                      fill: "color-mix(in srgb, var(--muted), var(--fv-ink) 4%)",
                      stroke: "color-mix(in srgb, var(--fv-ink) 25%, transparent)",
                      strokeWidth: 0.5,
                      outline: "none",
                    },
                  }}
                />
              ))
            }
          </Geographies>

          {/* Admin-1 region borders — only mounted (and only fetched) once the
              user zooms in, so the ~1.6MB layer never costs the default view.
              Non-interactive overlay: fill:none keeps the countries beneath, and
              pointerEvents:none leaves marker hover/click untouched. Stroke is
              divided by zoom to stay hairline as the group scales up. */}
          {detail && (
            <Geographies geography={ADMIN1_TOPO}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    style={{
                      default: {
                        fill: "none",
                        stroke: "color-mix(in srgb, var(--fv-ink) 22%, transparent)",
                        strokeWidth: 0.6 / zoom,
                        outline: "none",
                        pointerEvents: "none",
                      },
                      hover: {
                        fill: "none",
                        stroke: "color-mix(in srgb, var(--fv-ink) 22%, transparent)",
                        strokeWidth: 0.6 / zoom,
                        outline: "none",
                        pointerEvents: "none",
                      },
                      pressed: {
                        fill: "none",
                        stroke: "color-mix(in srgb, var(--fv-ink) 22%, transparent)",
                        strokeWidth: 0.6 / zoom,
                        outline: "none",
                        pointerEvents: "none",
                      },
                    }}
                  />
                ))
              }
            </Geographies>
          )}

          {arcs.map(({ s, anchor }) => (
            <Line
              key={`arc-${s.id}`}
              from={[s.lng, s.lat]}
              to={[anchor.lng, anchor.lat]}
              stroke="var(--fv-ochre)"
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
              <circle r={2.5} fill="var(--fv-ink)" opacity={0.55} />
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
                    stroke="var(--fv-ochre)"
                    strokeWidth={1.2}
                    strokeOpacity={0.9}
                  />
                )}
                <circle
                  r={emphasized ? r * 0.8 : r * 0.55}
                  fill={color}
                  fillOpacity={0.9}
                  stroke="var(--card)"
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
                      fill="var(--card)"
                      stroke="color-mix(in srgb, var(--fv-ink) 14%, transparent)"
                    />
                    <text
                      x={8}
                      y={13}
                      fontSize={7}
                      fill="var(--fv-ink)"
                      style={{ fontFamily: "var(--font-sans), system-ui, sans-serif", fontWeight: 600 }}
                    >
                      {s.headline}
                    </text>
                    <text
                      x={8}
                      y={25}
                      fontSize={6}
                      fill="color-mix(in srgb, var(--fv-ink) 60%, transparent)"
                      style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
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

      <div className="pointer-events-none absolute bottom-4 left-4 flex items-center gap-4 rounded-md border border-foreground/14 bg-card/85 px-3 py-2 text-[11px] text-foreground shadow-[var(--fv-shadow-md)] backdrop-blur">
        <LegendDot color={COLORS.bearish} label="Bearish" />
        <LegendDot color={COLORS.bullish} label="Bullish" />
        <LegendDot color={COLORS.neutral} label="Neutral" />
        <span className="ml-2 font-mono text-[10px] text-foreground/60">
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