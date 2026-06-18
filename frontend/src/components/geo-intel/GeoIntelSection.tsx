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
  const [running, setRunning] = useState(false);

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

  const runCycle = useCallback(async () => {
    setRunning(true);
    try {
      await api.geo.run();
    } catch {
      setRunning(false);
      return;
    }
    // The cycle runs in the background (~1 min); poll until signals land.
    let tries = 0;
    const poll = setInterval(async () => {
      tries += 1;
      try {
        const data = await api.geo.signals("all");
        setSignals(data);
        setPhase("ready");
        if (data.length > 0 || tries >= 8) {
          clearInterval(poll);
          setRunning(false);
        }
      } catch {
        if (tries >= 8) {
          clearInterval(poll);
          setRunning(false);
        }
      }
    }, 12000);
  }, []);

  return (
    <section className="flex h-full w-full flex-col bg-[#F5F1E8] text-[#1F1B16]">
      <header className="flex flex-col gap-3 border-b border-[rgba(31,27,22,0.14)] px-4 py-4 lg:flex-row lg:items-end lg:justify-between lg:px-8 lg:py-5">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.6)]">
            Dashboard · Section
          </p>
          <h1
            className="mt-1 text-2xl leading-none text-[#1F1B16] lg:text-3xl"
            style={{
              fontFamily: "var(--fv-font-fraunces), ui-serif, Georgia, serif",
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
        <div className="flex flex-wrap items-center gap-3 lg:gap-5">
          <button
            type="button"
            onClick={runCycle}
            disabled={running}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[#9A6B1F] px-3 font-mono text-[11px] text-[#9A6B1F] transition-colors hover:bg-[rgba(154,107,31,0.08)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? "Running…" : "Run cycle"}
          </button>
          <div className="flex items-center gap-4 font-mono text-[11px] text-[rgba(31,27,22,0.6)] lg:gap-6">
            <Stat label="Active" value={String(active)} />
            <Stat label="Tracked" value={String(filtered.length)} />
            <Stat label="Regions" value="7" />
          </div>
        </div>
      </header>

      <div className="flex flex-col lg:min-h-0 lg:flex-1 lg:flex-row">
        <div className="relative h-[55vh] p-4 lg:h-auto lg:min-h-0 lg:flex-1 lg:p-6">
          <div className="relative flex h-full w-full flex-col overflow-hidden rounded-xl border border-[rgba(31,27,22,0.14)] bg-[#FEFCF5] shadow-[0_4px_16px_rgba(31,27,22,0.08)] lg:block">
            <FilterBar
              categories={categories}
              onCategoriesChange={setCategories}
              direction={direction}
              onDirectionChange={setDirection}
              activeOnly={activeOnly}
              onActiveOnlyChange={setActiveOnly}
            />
            <div className="relative min-h-0 flex-1 lg:contents">
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