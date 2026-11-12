"use client";

import { Crosshair, Pin, PinOff, Play, X } from "lucide-react";
import { fmt, fmtDateTime, formatEur } from "@/lib/format";
import { eventDay, isAllDay, shortDay } from "../model/eventTiming";
import type { WorldAsset, WorldEvent } from "../model/types";
import s from "../world.module.css";
import { EventIllustration } from "./EventIllustration";
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
  asset: WorldAsset | null;
  pinned: boolean;
  onPin: () => void;
  onClose: () => void;
  onFocus: () => void;
  onReplay: () => void;
}

/** An all-day event has a date and no time; never print a midnight it did not happen at. */
function occurred(e: WorldEvent): string {
  if (!isAllDay(e)) return fmtDateTime(e.occurredAt);
  const day = eventDay(e);
  return `${shortDay(day, Date.parse(day))} ${day.slice(0, 4)} · todo el día`;
}

function headlineMetric(e: WorldEvent): { value: string; label: string } | null {
  const candidates: Partial<Record<WorldEvent["eventType"], [string, string, string]>> = {
    price_move_up: ["change_pct", "Variación diaria", "%"],
    price_move_down: ["change_pct", "Variación diaria", "%"],
    earnings_beat: ["surprise_pct", "Sorpresa vs. consenso", "%"],
    earnings_miss: ["surprise_pct", "Sorpresa vs. consenso", "%"],
    dividend_declared: ["dps", "Dividendo por acción", " €"],
    dividend_paid: ["net_eur", "Dividendo neto", " €"],
    position_added: ["value_eur", "Importe de compra", " €"],
    position_reduced: ["value_eur", "Importe de venta", " €"],
    position_closed: ["value_eur", "Valor de cierre", " €"],
    technical_signal: ["distance_pct", "Distancia a zona", "%"],
    options_alert: ["volume_ratio", "Ratio de volumen", "×"],
    week52_high: ["close", "Cierre", ""],
    week52_low: ["close", "Cierre", ""],
    volume_spike: ["volume_ratio", "Veces el volumen medio", "×"],
    stock_split: ["ratio", "Acciones nuevas por cada una", "×"],
    shares_received: ["quantity", "Acciones recibidas", ""],
    dividend_raised: ["change_pct", "Por acción frente a hace un año", "%"],
    dividend_cut: ["change_pct", "Por acción frente a hace un año", "%"],
    annual_report: ["fiscal_year", "Ejercicio", ""],
    geo_alert: ["importance", "Importancia", "/100"],
  };
  const spec = candidates[e.eventType];
  if (!spec) return null;
  const raw = e.metrics[spec[0]];
  if (typeof raw !== "number") return null;
  const sign = raw > 0 && spec[2] === "%" ? "+" : "";
  return { value: sign + fmt(raw, 2) + spec[2], label: spec[1] };
}

export function EventCard({ event: e, asset, pinned, onPin, onClose, onFocus, onReplay }: Readonly<Props>) {
  const highlight = headlineMetric(e);
  const identity = asset?.ticker ?? asset?.name ?? e.ticker ?? "PUEBLO";
  const assetName = asset?.name ?? (e.assetId ? "Empresa de la cartera" : "Actividad del pueblo");

  return (
    <article className={s.eventCard} aria-label={"Evento: " + e.title}>
      <header className={s.eventHeader}>
        <div className={s.eventIdentity}>
          <span className={s.eventTicker}>{identity.slice(0, 14).toUpperCase()}</span>
          <div className={s.eventIdentityText}>
            <strong>{assetName}</strong>
            <span className={s.meta}>{EVENT_TYPE_LABEL[e.eventType]}</span>
          </div>
        </div>
        <div className={s.eventHeaderActions}>
          <span className={s.eventSeverity + " " + (e.severity === "critical" ? s.eventSeverityCritical : e.severity === "important" ? s.eventSeverityImportant : "")}>
            {SEVERITY_LABEL[e.severity]}
          </span>
          <button className={s.btn} onClick={onClose} aria-label="Cerrar tarjeta" title="Cerrar">
            <X size={14} />
          </button>
        </div>
      </header>

      <div className={s.eventVisual}>
        <EventIllustration asset={asset} event={e} />
        <div className={s.eventVisualTags}>
          <span className={s.eventVisualTag}>{CATEGORY_LABEL[e.category]}</span>
          {e.confidence === "demo" && <span className={s.eventVisualTag}>Simulado</span>}
        </div>
      </div>

      {highlight && (
        <div className={s.eventImpact}>
          <strong className={s.eventImpactValue + " " + directionClass(e.direction)}>
            {highlight.value}
          </strong>
          <span className={s.eventImpactLabel}>{highlight.label}</span>
          <span className={s.eventDirection}>
            {DIRECTION_MARK[e.direction]} {DIRECTION_LABEL[e.direction]}
          </span>
        </div>
      )}

      <h3 className={s.eventTitle}>{e.title}</h3>
      <p className={s.eventSummary}>{e.summary}</p>

      <div className={s.eventSourceLine}>
        <span>{SOURCE_LABEL[e.sourceType] ?? e.sourceType}</span>
        <span>{occurred(e)}</span>
        <span>{CONFIDENCE_LABEL[e.confidence]}</span>
      </div>

      {asset && (
        <section className={s.eventPortfolioSnapshot} aria-label="Situación actual de la posición">
          <div className={s.eventSnapshotHeading}>Situación actual de la posición</div>
          <div className={s.eventSnapshotGrid}>
            <div>
              <span>Valor</span>
              <strong>{asset.marketValueEur === null ? "—" : formatEur(asset.marketValueEur)}</strong>
            </div>
            <div>
              <span>Peso</span>
              <strong>{asset.weightPct === null ? "—" : fmt(asset.weightPct, 2) + " %"}</strong>
            </div>
            <div>
              <span>Variación diaria</span>
              <strong className={directionClass(asset.dayChangePct === null ? "neutral" : asset.dayChangePct > 0 ? "positive" : asset.dayChangePct < 0 ? "negative" : "neutral")}>
                {asset.dayChangePct === null ? "—" : (asset.dayChangePct > 0 ? "+" : "") + fmt(asset.dayChangePct, 2) + " %"}
              </strong>
            </div>
          </div>
          <div className={s.eventSnapshotNote}>Datos actuales de cartera; no representan necesariamente el impacto histórico del evento.</div>
        </section>
      )}

      <details className={s.eventDetails}>
        <summary>Detalles y procedencia</summary>
        <table className={s.metrics}>
          <tbody>
            {Object.entries(e.metrics).map(([k, v]) => (
              <tr key={k}>
                <td>{METRIC_LABEL[k] ?? k}</td>
                <td>{metric(v)}</td>
              </tr>
            ))}
            <tr><td>Ocurrió</td><td>{occurred(e)}</td></tr>
            <tr><td>Observado por FinView</td><td>{fmtDateTime(e.observedAt)}</td></tr>
            <tr><td>Fuente</td><td>{SOURCE_LABEL[e.sourceType] ?? e.sourceType}</td></tr>
            <tr><td>Confianza</td><td>{CONFIDENCE_LABEL[e.confidence]}</td></tr>
          </tbody>
        </table>
        <div className={s.why}>
          <strong>¿Por qué ha ocurrido?</strong>
          <p>{e.why}</p>
        </div>
      </details>

      <footer className={s.actions}>
        <button className={s.btn + " " + s.linkBtn} onClick={onFocus} disabled={!e.assetId}>
          <Crosshair size={14} /> Enfocar
        </button>
        <button className={s.btn + " " + s.linkBtn} onClick={onReplay} disabled={!e.assetId}>
          <Play size={14} /> Ver escena
        </button>
        <button className={s.btn + " " + s.linkBtn + " " + (pinned ? s.btnOn : "")} onClick={onPin} aria-pressed={pinned}>
          {pinned ? <PinOff size={14} /> : <Pin size={14} />} {pinned ? "Desfijar" : "Fijar"}
        </button>
      </footer>
    </article>
  );
}
