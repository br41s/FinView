"use client";

import { useMemo, useState } from "react";
import type { TimeWindow, WorldAsset, WorldEvent } from "../model/types";
import s from "../world.module.css";
import { DIRECTION_MARK, SEVERITY_LABEL, WINDOW_LABEL } from "./labels";
import { directionClass } from "./EventCard";

type Order = "recent" | "priority";
const MAX_ROWS = 120;

interface Props {
  events: readonly WorldEvent[];
  assets: ReadonlyMap<string, WorldAsset>;
  window: TimeWindow;
  onWindow: (w: TimeWindow) => void;
  activeId: string | null;
  onOpen: (e: WorldEvent) => void;
  now: number;
  /** Replaces the "no events" line, e.g. to say why the real town has none yet. */
  emptyHint?: string;
}

function ago(iso: string, now: number): string {
  const m = Math.max(0, Math.round((now - Date.parse(iso)) / 60000));
  if (m < 1) return "ahora";
  if (m < 60) return `hace ${m} min`;
  const h = Math.round(m / 60);
  return h < 48 ? `hace ${h} h` : `hace ${Math.round(h / 24)} d`;
}

/** The event list lives outside the scene, so it keeps working however busy the town is. */
export function ActivityFeed({ events, assets, window: win, onWindow, activeId, onOpen, now, emptyHint }: Readonly<Props>) {
  const [order, setOrder] = useState<Order>("recent");
  const rows = useMemo(() => {
    const list = [...events];
    if (order === "priority") list.sort((a, b) => b.priorityScore - a.priorityScore);
    return list.slice(0, MAX_ROWS);
  }, [events, order]);

  return (
    <section className={`${s.card} ${s.panel} ${s.panelFill}`} aria-label="Actividad">
      <div className={s.panelHead}>
        <span>Actividad · {events.length}</span>
        <select className={s.select} value={order} onChange={(e) => setOrder(e.target.value as Order)} aria-label="Orden">
          <option value="recent">Más recientes</option>
          <option value="priority">Mayor prioridad</option>
        </select>
      </div>
      <div className={s.tabs} role="tablist" aria-label="Ventana de tiempo">
        {(Object.keys(WINDOW_LABEL) as TimeWindow[]).map((w) => (
          <button
            key={w}
            role="tab"
            aria-selected={win === w}
            className={`${s.btn} ${win === w ? s.btnOn : ""}`}
            onClick={() => onWindow(w)}
          >
            {WINDOW_LABEL[w]}
          </button>
        ))}
      </div>
      <div className={s.panelBody}>
        {rows.length === 0 && <p className={s.meta}>{emptyHint ?? "Sin eventos en esta ventana con los filtros actuales."}</p>}
        {rows.map((e) => {
          const a = e.assetId ? assets.get(e.assetId) : null;
          return (
            <button
              key={e.id}
              className={`${s.feedRow} ${s[`sev_${e.severity}`]} ${activeId === e.id ? s.feedRowActive : ""}`}
              onClick={() => onOpen(e)}
            >
              <div className={s.feedRowTop}>
                {a?.ticker && <span className={s.feedTickerSmall}>{a.ticker.slice(0, 10).toUpperCase()}</span>}
                <span className={s.feedTitle}>
                  <span className={directionClass(e.direction)} aria-hidden>{DIRECTION_MARK[e.direction]}</span>{" "}
                  {e.title}
                </span>
                <span className={s.feedSeverity}>{SEVERITY_LABEL[e.severity]}</span>
              </div>
              <div className={s.meta}>
                {a?.name ?? "Actividad del pueblo"} · {ago(e.occurredAt, now)}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
