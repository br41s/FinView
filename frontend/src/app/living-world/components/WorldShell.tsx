"use client";

import { ChevronLeft, Footprints, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import { NOT_ADVICE } from "@/lib/legal";
import type { Quality } from "../engine/quality";
import { useNow, usePrefersReducedMotion } from "../hooks/useClock";
import { supportsWebGL, useStats, useWorld, type StatsStore } from "../hooks/useWorld";
import { useWorldFilters } from "../hooks/useWorldFilters";
import { applyFilters, filterEvents } from "../model/filters";
import { generateDemoEvents, type DemoEventOptions } from "../model/fixtures";
import type { WorldAsset, WorldEvent } from "../model/types";
import { sceneSignature } from "../model/worldAssets";
import type { WorldMeta } from "../hooks/useWorldData";
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

interface Props {
  assets: readonly WorldAsset[];
  /** The last week's real events from the API; always empty in demo. */
  realEvents: readonly WorldEvent[];
  /** The fictional town (`?demo=1`): every holding and event is invented. */
  demo: boolean;
  meta: WorldMeta | null;
  onRefresh: (() => void) | null;
  refreshing: boolean;
  refreshFailed: boolean;
}

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "short" });

/**
 * The town for a set of assets: the user's portfolio, or the fictional one in demo. The real
 * town shows the last week's real events (daily moves, trades, dividends) and adds simulated
 * ones only while «Simular eventos» is on; anything simulated says so on its title, its card
 * and the toolbar. Turning the switch off removes the simulated events, never the real ones.
 */
export default function WorldShell({ assets, realEvents, demo, meta, onRefresh, refreshing, refreshFailed }: Readonly<Props>) {
  // The scene is rebuilt only when what it draws changes, not on every data refresh: a
  // price tick must not reset the camera. State set during render is React's pattern for
  // "derive from a prop, but only when it changes".
  const signature = sceneSignature(assets);
  const [scene, setScene] = useState({ signature, assets });
  if (scene.signature !== signature) setScene({ signature, assets });
  const sceneAssets = scene.assets;
  const byId = useMemo(() => new Map(assets.map((a) => [a.id, a])), [assets]);
  const now = useNow();
  const reducedMotion = usePrefersReducedMotion();

  // Simulated events: a title prefix in the real town, where they sit on real companies.
  const simulate = (o: DemoEventOptions): WorldEvent[] => {
    const batch = generateDemoEvents(assets, o);
    return demo ? batch : batch.map((e) => ({ ...e, title: `Simulado · ${e.title}` }));
  };
  const history = (): WorldEvent[] =>
    simulate({ nowMs: Date.now(), seed: 11, count: HISTORY_EVENTS, spanMs: WEEK, idPrefix: "hist" });

  const [simulated, setSimulated] = useState<WorldEvent[]>(() => (demo ? history() : []));
  const events = useMemo(
    () =>
      [...realEvents, ...simulated]
        .sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt))
        .slice(0, MAX_EVENTS),
    [realEvents, simulated],
  );
  const { filters, set, toggle, clear } = useWorldFilters();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [openEventId, setOpenEventId] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string[]>([]);
  const [panel, setPanel] = useState<Panel>(null);
  const [paused, setPaused] = useState(false);
  const [mode, setMode] = useState<ActivityMode>("normal");
  const [autoFocus, setAutoFocus] = useState(false);
  const [live, setLive] = useState(demo);
  const [quality, setQuality] = useState<Quality>(() =>
    typeof navigator !== "undefined" && (navigator.hardwareConcurrency ?? 8) <= 4 ? "low" : "medium",
  );
  const [canBack, setCanBack] = useState(false);
  const [tour, setTour] = useState(false);
  const [followTarget, setFollowTarget] = useState<string | null>(null);
  const [soundMuted, setSoundMuted] = useState(true);
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
      onTourChange: setTour,
      onFollowTarget: setFollowTarget,
    }),
    [],
  );
  const { world, failed, ready, statsStore } = useWorld(host, { assets: sceneAssets, quality, reducedMotion, callbacks });

  // An event joins the activity history, enters the scene queue and opens its own
  // story card. A burst chooses the highest-priority company event as the lead story.
  const emit = (batch: WorldEvent[]) => {
    setSimulated((prev) => [...batch, ...prev].slice(0, MAX_EVENTS));
    world.current?.enqueue(batch);
    const featured = [...batch]
      .filter((event) => event.assetId !== null)
      .sort((a, b) => b.priorityScore - a.priorityScore)[0] ?? batch[0];
    if (featured) setOpenEventId(featured.id);
  };

  const burst = (n: number) => {
    counter.current += 1;
    emit(simulate({ nowMs: Date.now(), seed: 1000 + counter.current, count: n, spanMs: 0, idPrefix: `burst${counter.current}` }));
  };

  const liveTick = useEffectEvent(() => {
    counter.current += 1;
    emit(simulate({ nowMs: Date.now(), seed: 5000 + counter.current, count: 1, spanMs: 0, idPrefix: `live${counter.current}` }));
  });

  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(liveTick, 7000);
    return () => window.clearInterval(id);
  }, [live]);

  // In the real town the switch adds simulated events on top of the real ones: turning it
  // on seeds a week of simulated history, turning it off takes everything simulated away.
  const setSimulating = (on: boolean) => {
    setLive(on);
    if (!demo) {
      setSimulated(on ? history() : []);
      setOpenEventId(null);
      setPinned([]);
    }
  };

  // Real events go through the scene once they arrive, so the buildings react to them. The
  // director skips ids it has already seen, so a refresh does not replay them; a rebuilt
  // scene has a new director and plays them again.
  useEffect(() => {
    if (ready) world.current?.enqueue(realEvents);
  }, [ready, realEvents, sceneAssets, world]);

  // The scene was rebuilt (the set of assets changed): the new one knows nothing of the
  // user's selection, so hand it back. Pause, mode, quality and filters are re-applied
  // by the effects below, which depend on the same `sceneAssets`.
  const reselect = useEffectEvent(() => {
    world.current?.select(selectedId && byId.has(selectedId) ? selectedId : null);
  });
  useEffect(() => {
    reselect();
  }, [sceneAssets, world]);

  // Mode and auto-focus are director settings; pause freezes the whole simulation.
  useEffect(() => {
    world.current?.setDirector(
      mode === "quiet"
        ? { quiet: true, autoFocus }
        : mode === "busy"
          ? { quiet: false, maxNormal: 6, maxTotal: 12, autoFocus }
          : { quiet: false, maxNormal: 3, maxTotal: 6, autoFocus },
    );
  }, [mode, autoFocus, world, sceneAssets]);
  useEffect(() => {
    world.current?.setPaused(paused);
  }, [paused, world, sceneAssets]);

  const visibility = useMemo(() => applyFilters(assets, events, filters, now), [assets, events, filters, now]);
  useEffect(() => {
    world.current?.setVisibility(visibility);
  }, [visibility, world, sceneAssets]);

  const feedEvents = useMemo(() => filterEvents(events, filters, now), [events, filters, now]);
  const eventById = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);

  const selected = selectedId ? (byId.get(selectedId) ?? null) : null;
  const cards = [...new Set([...pinned, ...(openEventId ? [openEventId] : [])])]
    .map((id) => eventById.get(id))
    .filter((e): e is WorldEvent => !!e)
    .slice(-MAX_PINNED - 1);

  const toggleSound = () => {
    if (world.current) {
      const next = world.current.toggleSound();
      setSoundMuted(next);
    }
  };

  const boardTrain = () => {
    if (followTarget === "SkyTrain Monorraíl") {
      world.current?.stopFollow();
      setFollowTarget(null);
    } else {
      world.current?.followMonorail();
    }
  };

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
            {demo ? (
              <>
                <span className={s.badge}>Maqueta demo (22 empresas)</span>
                <Link
                  href="/living-world"
                  className={`${s.badge} ${s.badgeAction}`}
                  title="Cambiar a los activos reales de tu cartera"
                >
                  Ver tu cartera →
                </Link>
              </>
            ) : (
              <>
                <span className={`${s.badge} ${s.badgeInfo}`}>
                  Tu cartera{meta?.pricesAsOf ? ` · precios del ${shortDate(meta.pricesAsOf)}` : ""}
                </span>
                <Link
                  href="/living-world?demo=1"
                  className={`${s.badge} ${s.badgeAction}`}
                  title="Ver maqueta viva completa con 22 empresas y campus"
                >
                  Ver demo (22 empresas) →
                </Link>
              </>
            )}
            {!demo && live && <span className={s.badge}>Eventos simulados</span>}
            <ClockBadge store={statsStore} />
          </div>
          <WorldSearch
            query={filters.query}
            assets={assets}
            onQuery={(q) => set({ query: q })}
            onPick={chooseAsset}
          />
          <WorldToolbar
            demo={demo}
            onRefresh={onRefresh}
            refreshing={refreshing}
            canBack={canBack}
            paused={paused}
            mode={mode}
            quality={quality}
            autoFocus={autoFocus}
            live={live}
            panel={panel}
            tour={tour}
            soundMuted={soundMuted}
            followingTrain={followTarget === "SkyTrain Monorraíl"}
            onToggleTour={() => world.current?.toggleTour()}
            onFit={() => world.current?.fit()}
            onBack={() => world.current?.back()}
            onRotate={(d) => world.current?.rotate(d)}
            onZoom={(f) => world.current?.zoom(f)}
            onPaused={setPaused}
            onMode={setMode}
            onQuality={setQuality}
            onAutoFocus={setAutoFocus}
            onLive={setSimulating}
            onBurst={() => burst(25)}
            onPanel={setPanel}
            onToggleSound={toggleSound}
            onBoardTrain={boardTrain}
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
              demo={demo}
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
              emptyHint={
                demo || live
                  ? undefined
                  : "Sin actividad real en los últimos 7 días: aquí aparecen tus compras, ventas y dividendos importados y los movimientos diarios de al menos un 2 %. Activa «Simular eventos» para ver cómo reaccionaría el pueblo."
              }
            />
          )}
        </div>
        </div>

        <div className={s.cards}>
          {cards.map((e) => (
            <EventCard
              key={e.id}
              event={e}
              asset={e.assetId ? (byId.get(e.assetId) ?? null) : null}
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

        {followTarget && (
          <div className={`${s.card} ${s.followPill}`}>
            <Footprints size={15} />
            <span>Siguiendo a <strong>{followTarget}</strong></span>
            <button
              className={s.btn}
              onClick={() => {
                world.current?.stopFollow();
                setFollowTarget(null);
              }}
              title="Dejar de seguir (Esc)"
            >
              <X size={14} /> Soltar
            </button>
          </div>
        )}

        <div className={s.footer}>
          <span>{NOT_ADVICE.short}</span>
          {meta && meta.unvalued > 0 && (
            <span>
              {meta.unvalued} sin valorar (sin precio): se dibujan pequeñas y marcadas, y los pesos se calculan sobre el resto
            </span>
          )}
          {meta && meta.unclassified > 0 && <span>{meta.unclassified} sin clasificar</span>}
          {refreshFailed && <span>No se pudo actualizar: se muestran los últimos datos</span>}
          <FpsLabel store={statsStore} />
        </div>
      </div>
    </div>
  );
}

function ClockBadge({ store }: Readonly<{ store: StatsStore }>) {
  const stats = useStats(store);
  if (!stats?.clockLabel) return null;
  return (
    <span className={`${s.badge} ${s.badgeInfo}`} title="Hora simulada en la ciudad y rutina de ciudadanos">
      🕒 {stats.clockLabel}
    </span>
  );
}

/** Subscribes on its own, so the 500 ms stats sample does not re-render the shell. */
function FpsLabel({ store }: Readonly<{ store: StatsStore }>) {
  const stats = useStats(store);
  if (!stats) return null;
  return (
    <span aria-label="Rendimiento y reloj">
      {stats.clockLabel ? `${stats.clockLabel} · ` : ""}{stats.fps} FPS · {stats.sites} edificios
    </span>
  );
}
