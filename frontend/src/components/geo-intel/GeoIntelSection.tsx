import { useCallback, useEffect, useMemo, useState } from "react";
import { GeoMap } from "./GeoMap";
import { SignalPanel } from "./SignalPanel";
import { FilterBar, CATEGORIES, type DirectionFilter } from "./FilterBar";
import { MapLoading, MapEmpty, MapError } from "./MapStates";
import { type GeoSignal } from "@/lib/geo";
import { api } from "@/lib/api";

export function GeoIntelSection() {
  const [signals, setSignals] = useState<GeoSignal[]>([]);
  const [selected, setSelected] = useState<GeoSignal | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [categories, setCategories] = useState<GeoSignal["category"][]>(CATEGORIES);
  const [direction, setDirection] = useState<DirectionFilter>("all");
  const [activeOnly, setActiveOnly] = useState(true);
  // Phase starts as 'loading' on both server and client (no Date.now/random in
  // initial render), which also gates time/coordinate values that drift across
  // SSR/CSR and would otherwise cause hydration mismatches.
  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");

  const load = useCallback(() => {
    setPhase("loading");
    api.geo
      .signals("all")
      .then((data) => {
        setSignals(data);
        setPhase("ready");
      })
      .catch(() => setPhase("error"));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    return signals.filter((s) => {
      if (activeOnly && s.status !== "active") return false;
      if (!categories.includes(s.category)) return false;
      if (direction !== "all" && s.direction !== direction) return false;
      return true;
    });
  }, [signals, categories, direction, activeOnly]);

  const active = filtered.filter((s) => s.status === "active").length;

  const retry = load;

  return (
    <section className="flex h-full w-full flex-col bg-[#F5F1E8] text-[#1F1B16]">
      <header className="flex items-end justify-between border-b border-[rgba(31,27,22,0.14)] px-8 py-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.6)]">
            Dashboard · Section
          </p>
          <h1
            className="mt-1 text-3xl leading-none text-[#1F1B16]"
            style={{
              fontFamily: "Fraunces, ui-serif, Georgia, serif",
              fontWeight: 500,
              letterSpacing: "-0.01em",
            }}
          >
            Geo-Intel
          </h1>
          <p className="mt-1 text-[13px] text-[rgba(31,27,22,0.6)]">
            Geopolitical & natural events, plotted as financial signals.
          </p>
        </div>
        <div className="flex items-center gap-6 font-mono text-[11px] text-[rgba(31,27,22,0.6)]">
          <Stat label="Active" value={String(active)} />
          <Stat label="Tracked" value={String(filtered.length)} />
          <Stat label="Regions" value="7" />
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div className="relative min-h-0 flex-1 p-6">
          <div className="relative h-full w-full overflow-hidden rounded-xl border border-[rgba(31,27,22,0.14)] bg-[#FEFCF5] shadow-[0_4px_16px_rgba(31,27,22,0.08)]">
            <FilterBar
              categories={categories}
              onCategoriesChange={setCategories}
              direction={direction}
              onDirectionChange={setDirection}
              activeOnly={activeOnly}
              onActiveOnlyChange={setActiveOnly}
            />
            {phase === "loading" ? (
              <MapLoading />
            ) : phase === "error" ? (
              <MapError onRetry={retry} />
            ) : filtered.length === 0 ? (
              <MapEmpty />
            ) : (
              <GeoMap
                signals={filtered}
                selectedId={selected?.id ?? null}
                hoveredId={hoveredId}
                onHoverSignal={setHoveredId}
                onSelectSignal={(s) => setSelected(s)}
              />
            )}
          </div>
        </div>
        <SignalPanel
          signals={filtered}
          selected={selected}
          hoveredId={hoveredId}
          onHover={setHoveredId}
          onSelect={setSelected}
          loading={phase === "loading"}
        />
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
        {label}
      </span>
      <span className="text-[15px] text-[#1F1B16]">{value}</span>
    </div>
  );
}