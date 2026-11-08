"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { NOT_ADVICE } from "@/lib/legal";
import type { Quality } from "../engine/quality";
import { useNow, nowMs, usePrefersReducedMotion } from "../hooks/useClock";
import { supportsWebGL, useStats, useWorld, type StatsStore } from "../hooks/useWorld";
import { useWorldFilters } from "../hooks/useWorldFilters";
import { applyFilters, filterEvents } from "../model/filters";
import { demoAssets, generateDemoEvents } from "../model/fixtures";
import type { WorldAsset, WorldEvent } from "../model/types";
import s from "../world.module.css";
import { ActivityFeed } from "./ActivityFeed";
import { BuildingInspector } from "./BuildingInspector";
import { EventCard } from "./EventCard";
import { ActiveFilterChips, WorldFiltersPanel } from "./WorldFilters";
import { WorldSearch } from "./WorldSearch";
import { WorldToolbar, type ActivityMode, type Panel } from "./WorldToolbar";

const HISTORY_EVENTS = 160;
const WEEK = 7 * 24 * 3_600_000;
const MAX_EVENTS = 800;
const MAX_PINNED = 3;

/** Phase 0: every holding and every event is fictional and lives only in this component. */
export default function WorldShell() {
  const assets = useMemo<WorldAsset[]>(() => demoAssets(), []);
  const byId = useMemo(() => new Map(assets.map((a) => [a.id, a])), [assets]);
  const now = useNow();
  const reducedMotion = usePrefersReducedMotion();

  const [events, setEvents] = useState<WorldEvent[]>(() =>
    generateDemoEvents(assets, { nowMs: nowMs(), seed: 11, count: HISTORY_EVENTS, spanMs: WEEK, idPrefix: "hist" }),
  );
  const { filters, set, toggle, clear } = useWorldFilters();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openEventId, setOpenEventId] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string[]>([]);
  const [panel, setPanel] = useState<Panel>(null);
  const [paused, setPaused] = useState(false);
  const [mode, setMode] = useState<ActivityMode>("normal");
  const [autoFocus, setAutoFocus] = useState(false);
  const [live, setLive] = useState(true);
  const [quality, setQuality] = useState<Quality>(() =>
    typeof navigator !== "undefined" && (navigator.hardwareConcurrency ?? 8) <= 4 ? "low" : "medium",
  );
  const [canBack, setCanBack] = useState(false);
  const [webgl] = useState(supportsWebGL);
  const host = useRef<HTMLDivElement | null>(null);
  const counter = useRef(0);

  const callbacks = useMemo(
    () => ({
      onSelect: (id: string | null) => {
        setSelectedId(id);
        // On a phone the inspector and a panel would stack over the scene.
        if (id && window.innerWidth < 760) setPanel(null);
      },
      onHover: () => undefined,
      onFocusKey: () => undefined,
      onPerformance: () => undefined,
      onStats: () => undefined,
      onCanBack: setCanBack,
    }),
    [],
  );
  const { world, failed, ready, statsStore } = useWorld(host, { assets, quality, reducedMotion, callbacks });

  // Emitting an event is one action: it joins the history and queues for the stage.
  const emit = (batch: WorldEvent[]) => {
    setEvents((prev) => [...batch, ...prev].slice(0, MAX_EVENTS));
    world.current?.enqueue(batch);
  };

  const burst = (n: number) => {
    counter.current += 1;
    emit(generateDemoEvents(assets, { nowMs: Date.now(), seed: 1000 + counter.current, count: n, spanMs: 0, idPrefix: `burst${counter.current}` }));
  };

  const liveTick = useEffectEvent(() => {
    counter.current += 1;
    emit(generateDemoEvents(assets, { nowMs: Date.now(), seed: 5000 + counter.current, count: 1, spanMs: 0, idPrefix: `live${counter.current}` }));
  });

  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(liveTick, 7000);
    return () => window.clearInterval(id);
  }, [live]);

  // Mode and auto-focus are director settings; pause freezes the whole simulation.
  useEffect(() => {
    world.current?.setDirector(
      mode === "quiet"
        ? { quiet: true, autoFocus }
        : mode === "busy"
          ? { quiet: false, maxNormal: 6, maxTotal: 12, autoFocus }
          : { quiet: false, maxNormal: 3, maxTotal: 6, autoFocus },
    );
  }, [mode, autoFocus, world, assets]);
  useEffect(() => {
    world.current?.setPaused(paused);
  }, [paused, world, assets]);

  const visibility = useMemo(() => applyFilters(assets, events, filters, now), [assets, events, filters, now]);
  useEffect(() => {
    world.current?.setVisibility(visibility);
  }, [visibility, world, assets]);

  const feedEvents = useMemo(() => filterEvents(events, filters, now), [events, filters, now]);
  const eventById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);

  const selected = selectedId ? (byId.get(selectedId) ?? null) : null;
  const cards = [...new Set([...pinned, ...(openEventId ? [openEventId] : [])])]
    .map((id) => eventById.get(id))
    .filter((e): e is WorldEvent => !!e)
    .slice(-MAX_PINNED - 1);

  const chooseAsset = (a: WorldAsset) => {
    world.current?.select(a.id);
    world.current?.focusAsset(a.id);
    setSelectedId(a.id);
  };

  const openFromFeed = (e: WorldEvent) => {
    setOpenEventId(e.id);
    if (e.assetId) {
      world.current?.select(e.assetId);
      world.current?.focusAsset(e.assetId);
      setSelectedId(e.assetId);
    }
  };

  if (!webgl || failed) {
    return (
      <div className={s.root}>
        <div className={s.center}>
          <div className={`${s.card}`}>
            <h2 style={{ marginTop: 0 }}>No se puede mostrar el mundo</h2>
            <p>{failed ?? "Tu navegador o dispositivo no ofrece WebGL, necesario para la escena 3D."}</p>
            <Link className={`${s.btn} ${s.linkBtn}`} href="/dashboard">
              Volver al dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={s.root}>
      <div ref={host} className={s.host} />
      {!ready && (
        <div className={s.center} aria-live="polite">
          <div className={s.card}>Construyendo el pueblo…</div>
        </div>
      )}

      <div className={s.ui}>
        <div className={s.top}>
        <div className={s.topbar}>
          <div className={`${s.card} ${s.brand}`}>
            <Link href="/dashboard" aria-label="Volver al dashboard">
              <ChevronLeft size={16} /> Dashboard
            </Link>
            <span className={s.title}>Mundo vivo</span>
            <span className={s.badge}>Datos ficticios</span>
          </div>
          <WorldSearch
            query={filters.query}
            assets={assets}
            onQuery={(q) => set({ query: q })}
            onPick={chooseAsset}
          />
          <WorldToolbar
            canBack={canBack}
            paused={paused}
            mode={mode}
            quality={quality}
            autoFocus={autoFocus}
            live={live}
            panel={panel}
            onFit={() => world.current?.fit()}
            onBack={() => world.current?.back()}
            onRotate={(d) => world.current?.rotate(d)}
            onZoom={(f) => world.current?.zoom(f)}
            onPaused={setPaused}
            onMode={setMode}
            onQuality={setQuality}
            onAutoFocus={setAutoFocus}
            onLive={setLive}
            onBurst={() => burst(25)}
            onPanel={setPanel}
          />
        </div>

        <ActiveFilterChips filters={filters} onSet={set} onToggle={toggle} />
        </div>

        <div className={s.mid}>
        <div className={s.leftCol}>
          {panel === "filters" && (
            <WorldFiltersPanel filters={filters} assets={assets} onSet={set} onToggle={toggle} onClear={clear} />
          )}
        </div>

        <div className={s.rightCol}>
          {selected && (
            <BuildingInspector
              asset={selected}
              events={events}
              onClose={() => {
                world.current?.select(null);
                setSelectedId(null);
              }}
              onFocus={() => world.current?.focusAsset(selected.id)}
              onFollow={() => world.current?.followAsset(selected.id)}
              onOpenEvent={openFromFeed}
            />
          )}
          {panel === "feed" && (
            <ActivityFeed
              events={feedEvents}
              assets={byId}
              window={filters.window}
              onWindow={(w) => set({ window: w })}
              activeId={openEventId}
              onOpen={openFromFeed}
              now={now}
            />
          )}
        </div>
        </div>

        <div className={s.cards}>
          {cards.map((e) => (
            <EventCard
              key={e.id}
              event={e}
              assetName={e.assetId ? (byId.get(e.assetId)?.name ?? null) : null}
              pinned={pinned.includes(e.id)}
              onPin={() =>
                setPinned((p) => (p.includes(e.id) ? p.filter((x) => x !== e.id) : [...p, e.id].slice(-MAX_PINNED)))
              }
              onClose={() => {
                setPinned((p) => p.filter((x) => x !== e.id));
                if (openEventId === e.id) setOpenEventId(null);
              }}
              onFocus={() => e.assetId && world.current?.focusAsset(e.assetId)}
              onReplay={() => world.current?.replay(e)}
            />
          ))}
        </div>

        <div className={s.footer}>
          <span>{NOT_ADVICE.short}</span>
          <FpsLabel store={statsStore} />
        </div>
      </div>
    </div>
  );
}

/** Subscribes on its own, so the 500 ms stats sample does not re-render the shell. */
function FpsLabel({ store }: Readonly<{ store: StatsStore }>) {
  const stats = useStats(store);
  if (!stats) return null;
  return (
    <span aria-label="Rendimiento">
      {stats.fps} FPS · {stats.sites} edificios
    </span>
  );
}
