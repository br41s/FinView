import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Globe } from "lucide-react";
import { GeoMap } from "./GeoMap";
import { SignalPanel } from "./SignalPanel";
import { FilterBar, CATEGORIES, type DirectionFilter } from "./FilterBar";
import { MapLoading, MapEmpty, MapError } from "./MapStates";
import { formatAccuracyLine, macroRegimeBadge, type GeoAccuracy, type GeoSignal } from "@/lib/geo";
import { geoHealth } from "@/lib/geoHealth";
import { api, type GeoSchedulerStatus } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/PageHeader";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";
import { AiDisclaimer, PastPerformanceNote } from "@/components/AiDisclaimer";

export function GeoIntelSection() {
  const { privacy, togglePrivacy } = usePrivacyToggle();
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
  const [monitor, setMonitor] = useState<GeoSchedulerStatus | null>(null);
  const [togglingMonitor, setTogglingMonitor] = useState(false);
  // Outcome of the last manual run. A cycle that ingests nothing is a result,
  // not silence, and the button used to report both the same way: by stopping.
  const [runOutcome, setRunOutcome] = useState<string | null>(null);
  // How often the checkpoints were right. Enrichment: the page works without
  // it, so a failure logs and leaves the line out rather than blocking.
  const [accuracy, setAccuracy] = useState<GeoAccuracy | null>(null);
  const pollTick = useRef(0);

  // Does not flip phase to "loading" itself: on mount it already is, and the
  // retry button sets it before calling this.
  const load = useCallback(() => {
    api.geo
      .signals("all")
      .then((data) => {
        setSignals(data);
        setPhase("ready");
      })
      .catch(() => setPhase("error"));
  }, []);

  const loadMonitor = useCallback(() => {
    api.geo
      .schedulerStatus()
      .then(setMonitor)
      .catch(bestEffort("geo monitor status"));
  }, []);

  const loadAccuracy = useCallback(() => {
    api.geo.accuracy().then(setAccuracy).catch(bestEffort("geo accuracy"));
  }, []);

  useEffect(() => {
    load();
    loadMonitor();
    loadAccuracy();
  }, [load, loadMonitor, loadAccuracy]);

  // Deep link: /geo-intel?ticker=X selects the newest signal affecting X. The
  // Options Monitor only offers the link when a signal actually exists, but the
  // URL can be stale or hand-typed, so an unmatched ticker is a silent no-op.
  const tickerHintRef = useRef<string | null>(null);
  useEffect(() => {
    tickerHintRef.current = new URLSearchParams(window.location.search).get("ticker");
  }, []);
  useEffect(() => {
    const hint = tickerHintRef.current;
    if (!hint || signals.length === 0) return;
    tickerHintRef.current = null;
    const upper = hint.toUpperCase();
    const match = signals.find((s) =>
      s.tickers.some((t) => t.symbol.toUpperCase() === upper),
    );
    if (match) setSelected(match);
  }, [signals]);

  // Silent refresh so new signals/alerts appear without user interaction.
  useEffect(() => {
    const id = setInterval(() => {
      api.geo
        .signals("all")
        .then((data) => {
          setSignals(data);
          setPhase((p) => (p === "error" ? "ready" : p));
        })
        .catch(bestEffort("geo signals refresh"));
      loadMonitor();
      // The hit rate only moves when the 30-min cron runs: a grouped scan over
      // the whole checkpoint history every 60 s was 30× over-fetching.
      pollTick.current += 1;
      if (pollTick.current % 10 === 0) loadAccuracy();
    }, 60_000);
    return () => clearInterval(id);
  }, [loadMonitor, loadAccuracy]);

  const toggleMonitor = useCallback(async () => {
    if (!monitor) return;
    setTogglingMonitor(true);
    try {
      if (monitor.running) await api.geo.stopScheduler();
      else await api.geo.startScheduler();
      loadMonitor();
    } catch {
      // status refetch below reflects reality
    } finally {
      setTogglingMonitor(false);
    }
  }, [monitor, loadMonitor]);

  const filtered = useMemo(() => {
    return signals.filter((s) => {
      if (activeOnly && s.status !== "active") return false;
      if (!categories.includes(s.category)) return false;
      if (direction !== "all" && s.direction !== direction) return false;
      return true;
    });
  }, [signals, categories, direction, activeOnly]);

  const active = filtered.filter((s) => s.status === "active").length;
  const regions = useMemo(
    () => new Set(filtered.map((s) => s.location).filter(Boolean)).size,
    [filtered],
  );
  const lastSignal = monitor?.last_signal_at
    ? new Date(monitor.last_signal_at).toLocaleString()
    : "—";
  // Recomputed on every poll (the status refetches on the same 60s tick), so a
  // pipeline that stops during the session shows up without a reload.
  const health = useMemo(() => geoHealth(monitor), [monitor]);
  const regimeBadge = useMemo(() => macroRegimeBadge(monitor?.macro), [monitor]);
  // Null until the first fetch lands, so nothing time-derived renders on the
  // server and the line simply stays absent when the endpoint is unreachable.
  const accuracyLine = useMemo(() => formatAccuracyLine(accuracy), [accuracy]);

  const retry = useCallback(() => {
    setPhase("loading");
    load();
  }, [load]);

  const runCycle = useCallback(async () => {
    setRunning(true);
    setRunOutcome(null);
    try {
      const result = await api.geo.run();
      if (result.status === "completed") {
        const data = await api.geo.signals("all");
        setSignals(data);
        setPhase("ready");
        // Say what the cycle did. "0 eventos" is the fastest way to tell an
        // ingest problem from a rules-matched-nothing day, and the button
        // returning to its idle label said neither.
        setRunOutcome(
          `Ciclo completado: ${result.events ?? 0} eventos, ` +
            `${result.new_signals ?? 0} señales nuevas.`,
        );
        loadMonitor();
        setRunning(false);
        return;
      }
    } catch (error) {
      // The cycle failing is the single most useful thing this page can tell
      // its owner; swallowing it is what let a dead pipeline look idle.
      setRunOutcome(
        error instanceof Error ? error.message : "No se pudo ejecutar el ciclo.",
      );
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
  }, [loadMonitor]);

  return (
    <section className="flex h-full w-full flex-col bg-[#F5F1E8] text-[#1F1B16]">
      <PageHeader
        icon={Globe}
        title="Ideas"
        subtitle="Eventos geopolíticos y naturales, y los activos que históricamente se han movido con ellos."
        current="/geo-intel"
        privacy={privacy}
        onTogglePrivacy={togglePrivacy}
        className="border-b border-border p-6"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={runCycle} disabled={running}>
              {running ? "Running…" : "Run cycle"}
            </Button>
            <Button
              variant={monitor?.running ? "default" : "outline"}
              size="sm"
              onClick={toggleMonitor}
              disabled={togglingMonitor || monitor === null || monitor.external_scheduler}
            >
              {monitor?.external_scheduler
                ? "Cloud Scheduler"
                : monitor?.running
                ? `Monitor ON · ${monitor.interval_minutes}m`
                : "Start monitor"}
            </Button>
            <div className="flex items-center gap-4 font-mono text-[11px] text-muted-foreground lg:gap-6">
              <Stat label="Active" value={String(active)} />
              <Stat label="Tracked" value={String(filtered.length)} />
              <Stat label="Regions" value={String(regions)} />
              <Stat label="Last signal" value={lastSignal} />
            </div>
          </>
        }
      >
        {(health || runOutcome || regimeBadge) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
            {health && (
              <span className={HEALTH_TONE[health.tone]} role="status">
                {health.tone === "ok" ? "●" : "▲"} {health.message}
              </span>
            )}
            {runOutcome && <span className="text-muted-foreground">{runOutcome}</span>}
            {regimeBadge && (
              <span
                className="rounded border px-1.5 py-0.5"
                style={{
                  // the warm palette HEALTH_TONE uses beside it, not Tailwind's generic reds
                  color: regimeBadge.tone === "warn" ? "#9B3D2C" : regimeBadge.tone === "ok" ? "#6B7A3A" : "rgba(31,27,22,0.6)",
                  borderColor: regimeBadge.tone === "warn" ? "rgba(155,61,44,0.3)" : regimeBadge.tone === "ok" ? "rgba(107,122,58,0.3)" : "rgba(31,27,22,0.15)",
                  backgroundColor: regimeBadge.tone === "warn" ? "rgba(155,61,44,0.08)" : regimeBadge.tone === "ok" ? "rgba(107,122,58,0.08)" : "rgba(31,27,22,0.04)",
                }}
                role="status"
                title={regimeBadge.title}
              >
                {regimeBadge.label}
              </span>
            )}
          </div>
        )}
        {accuracyLine && (
          <p
            className="text-[11px] text-[rgba(31,27,22,0.5)]"
            style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
          >
            {accuracyLine}
          </p>
        )}
      </PageHeader>

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

      <footer className="space-y-1 border-t border-border px-6 py-3">
        <AiDisclaimer />
        {accuracyLine && <PastPerformanceNote />}
      </footer>
    </section>
  );
}

// The section paints its own warm canvas rather than using theme tokens, so the
// health line follows it: ochre for "look at this", the map's bearish red for
// "it is broken".
const HEALTH_TONE = {
  ok: "text-[rgba(31,27,22,0.6)]",
  warn: "text-[#825416]",
  down: "text-[#9B3D2C]",
} as const;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col items-end">
      <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <span className="text-[15px] text-foreground">{value}</span>
    </div>
  );
}
