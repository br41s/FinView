"use client";

import { Crosshair, Pin, PinOff, Play, X } from "lucide-react";
import { fmt, fmtDateTime } from "@/lib/format";
import type { WorldEvent } from "../model/types";
import s from "../world.module.css";
import {
  CATEGORY_LABEL,
  CONFIDENCE_LABEL,
  DIRECTION_LABEL,
  DIRECTION_MARK,
  EVENT_TYPE_LABEL,
  METRIC_LABEL,
  SEVERITY_LABEL,
  SOURCE_LABEL,
} from "./labels";

/** An unknown figure is a dash, never a zero. */
function metric(v: number | string | null): string {
  if (v === null) return "—";
  if (typeof v === "number") return fmt(v, Number.isInteger(v) ? 0 : 2);
  return v;
}

export function directionClass(d: WorldEvent["direction"]) {
  return d === "positive" ? s.up : d === "negative" ? s.down : "";
}

interface Props {
  event: WorldEvent;
  assetName: string | null;
  pinned: boolean;
  onPin: () => void;
  onClose: () => void;
  onFocus: () => void;
  onReplay: () => void;
}

/**
 * Everything a card says is a fact with a source, never prose alone: exact metrics,
 * when it happened versus when FinView saw it, confidence, and the rule that fired.
 */
export function EventCard({ event: e, assetName, pinned, onPin, onClose, onFocus, onReplay }: Readonly<Props>) {
  return (
    <article className={`${s.card} ${s.eventCard}`} aria-label={`Evento: ${e.title}`}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <div className={s.tags}>
          <span className={s.tag}>{CATEGORY_LABEL[e.category]}</span>
          <span className={s.tag}>{SEVERITY_LABEL[e.severity]}</span>
          <span className={`${s.tag} ${directionClass(e.direction)}`}>
            {DIRECTION_MARK[e.direction]} {DIRECTION_LABEL[e.direction]}
          </span>
          {e.confidence === "demo" && <span className={`${s.tag} ${s.tagDemo}`}>Simulado</span>}
        </div>
        <button className={s.btn} onClick={onClose} aria-label="Cerrar tarjeta" title="Cerrar">
          <X size={14} />
        </button>
      </div>

      <h3>{e.title}</h3>
      <div className={s.meta}>
        {EVENT_TYPE_LABEL[e.eventType]}
        {assetName ? ` · ${assetName}` : ""}
      </div>
      <p style={{ margin: "6px 0" }}>{e.summary}</p>

      <table className={s.metrics}>
        <tbody>
          {Object.entries(e.metrics).map(([k, v]) => (
            <tr key={k}>
              <td>{METRIC_LABEL[k] ?? k}</td>
              <td>{metric(v)}</td>
            </tr>
          ))}
          <tr>
            <td>Ocurrió</td>
            <td>{fmtDateTime(e.occurredAt)}</td>
          </tr>
          <tr>
            <td>Observado por FinView</td>
            <td>{fmtDateTime(e.observedAt)}</td>
          </tr>
          <tr>
            <td>Fuente</td>
            <td>{SOURCE_LABEL[e.sourceType] ?? e.sourceType}</td>
          </tr>
          <tr>
            <td>Confianza</td>
            <td>{CONFIDENCE_LABEL[e.confidence]}</td>
          </tr>
        </tbody>
      </table>

      <details className={s.why}>
        <summary>¿Por qué ha ocurrido?</summary>
        <p style={{ margin: "6px 0 0" }}>{e.why}</p>
      </details>

      <div className={s.actions}>
        <button className={`${s.btn} ${s.linkBtn}`} onClick={onFocus} disabled={!e.assetId}>
          <Crosshair size={14} /> Enfocar
        </button>
        <button className={`${s.btn} ${s.linkBtn}`} onClick={onReplay} disabled={!e.assetId}>
          <Play size={14} /> Reproducir
        </button>
        <button className={`${s.btn} ${s.linkBtn} ${pinned ? s.btnOn : ""}`} onClick={onPin} aria-pressed={pinned}>
          {pinned ? <PinOff size={14} /> : <Pin size={14} />} {pinned ? "Desfijar" : "Fijar"}
        </button>
      </div>
    </article>
  );
}
