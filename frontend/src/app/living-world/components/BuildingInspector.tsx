"use client";

import { Crosshair, Footprints, X } from "lucide-react";
import Link from "next/link";
import { fmt, fmtPct, formatEur } from "@/lib/format";
import { ARCHETYPE_LABEL } from "../model/archetypes";
import type { WorldAsset, WorldEvent } from "../model/types";
import s from "../world.module.css";
import { ASSET_TYPE_LABEL, EVENT_TYPE_LABEL } from "./labels";

interface Props {
  asset: WorldAsset;
  /** Fictional holdings: there is no real position to link to. */
  demo: boolean;
  events: readonly WorldEvent[];
  onClose: () => void;
  onFocus: () => void;
  onFollow: () => void;
  onOpenEvent: (e: WorldEvent) => void;
}

const eur = (v: number | null) => (v === null ? "—" : formatEur(v));

/**
 * A light card, not a dashboard (spec §12.2). Cost and P/L appear only when FinView knows
 * them; otherwise a dash, because an unknown cost is not a cost of zero.
 */
export function BuildingInspector({ asset: a, demo, events, onClose, onFocus, onFollow, onOpenEvent }: Readonly<Props>) {
  const recent = events.filter((e) => e.assetId === a.id).slice(0, 6);
  return (
    <aside className={`${s.card} ${s.inspector}`} aria-label={`Edificio: ${a.name}`}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <div>
          <h2>{a.name}</h2>
          <div className={s.meta}>
            {a.ticker ?? "Sin ticker"} · {a.isin}
          </div>
        </div>
        <button className={s.btn} onClick={onClose} aria-label="Cerrar inspector" title="Cerrar">
          <X size={14} />
        </button>
      </div>

      <div className={s.tags} style={{ marginTop: 6 }}>
        <span className={s.tag}>{ARCHETYPE_LABEL[a.archetype]}</span>
        {ASSET_TYPE_LABEL[a.assetType] !== ARCHETYPE_LABEL[a.archetype] && (
          <span className={s.tag}>{ASSET_TYPE_LABEL[a.assetType]}</span>
        )}
        {!a.classified && <span className={`${s.tag} ${s.tagDemo}`}>Sin clasificar</span>}
        {a.closed && <span className={`${s.tag} ${s.tagDemo}`}>Posición cerrada · en ruinas</span>}
        {!a.closed && a.marketValueEur === null && <span className={`${s.tag} ${s.tagDemo}`}>Valoración desconocida</span>}
      </div>

      {a.closed ? (
        // What the ledger says about a holding that is gone. No «gain»: a sum of sales minus
        // buys is not a realised result (that is the FIFO engine's, per fiscal year).
        <dl className={s.kv}>
          <dt>Cerrada el</dt>
          <dd>{new Date(`${a.closed.on}T12:00:00`).toLocaleDateString("es-ES", { day: "numeric", month: "long", year: "numeric" })}</dd>
          <dt>Invertido en compras</dt>
          <dd>{eur(a.closed.investedEur)}</dd>
          <dt>Recibido en ventas</dt>
          <dd>{eur(a.closed.soldEur)}</dd>
          <dt>Dividendos cobrados</dt>
          <dd>{eur(a.closed.dividendsEur)}</dd>
          <dt>Cuentas</dt>
          <dd>{a.brokers.length} · {a.brokers.join(", ")}</dd>
        </dl>
      ) : (
      <dl className={s.kv}>
        <dt>Valor</dt>
        <dd>{eur(a.marketValueEur)}</dd>
        <dt>Peso en cartera</dt>
        <dd>{a.weightPct === null ? "—" : `${fmt(a.weightPct, 2)} %`}</dd>
        <dt>Variación diaria</dt>
        <dd>{fmtPct(a.dayChangePct, 2)}</dd>
        <dt>Coste</dt>
        <dd>{eur(a.totalCostEur)}</dd>
        <dt>Resultado latente</dt>
        <dd>{eur(a.unrealizedPlEur)}</dd>
        <dt>Cuentas</dt>
        <dd>{a.brokers.length} · {a.brokers.join(", ")}</dd>
      </dl>
      )}

      <div className={s.actions}>
        <button className={`${s.btn} ${s.linkBtn}`} onClick={onFocus}>
          <Crosshair size={14} /> Enfocar
        </button>
        {!a.closed && (
          <button className={`${s.btn} ${s.linkBtn}`} onClick={onFollow}>
            <Footprints size={14} /> Seguir trabajador
          </button>
        )}
      </div>
      {demo ? (
        <p className={s.meta} style={{ margin: "8px 0 0" }}>
          Datos ficticios: con tu cartera real, aquí aparecerán los enlaces a Cartera, Técnico y Derivados.
        </p>
      ) : (
        <div className={s.actions} style={{ marginTop: 8 }}>
          <Link className={`${s.btn} ${s.linkBtn}`} href="/portfolio">
            Cartera
          </Link>
          {a.ticker && (
            <>
              <Link className={`${s.btn} ${s.linkBtn}`} href={`/zonas-clave?ticker=${encodeURIComponent(a.ticker)}`}>
                Técnico
              </Link>
              <Link className={`${s.btn} ${s.linkBtn}`} href={`/options?ticker=${encodeURIComponent(a.ticker)}`}>
                Derivados
              </Link>
            </>
          )}
        </div>
      )}

      <div className={s.groupTitle} style={{ marginTop: 10 }}>
        Actividad reciente
      </div>
      {recent.length === 0 && <p className={s.meta}>Sin eventos todavía.</p>}
      {recent.map((e) => (
        <button key={e.id} className={`${s.feedRow} ${s[`sev_${e.severity}`]}`} onClick={() => onOpenEvent(e)}>
          <div className={s.feedTitle}>{EVENT_TYPE_LABEL[e.eventType]}</div>
          <div className={s.meta}>{e.title}</div>
        </button>
      ))}
    </aside>
  );
}
