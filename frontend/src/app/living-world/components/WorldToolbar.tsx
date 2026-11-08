"use client";

import {
  Crosshair,
  Filter,
  List,
  Maximize,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Sparkles,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { QUALITY_LABEL, type Quality } from "../engine/quality";
import s from "../world.module.css";

export type ActivityMode = "quiet" | "normal" | "busy";
export type Panel = "filters" | "feed" | null;

interface Props {
  canBack: boolean;
  paused: boolean;
  mode: ActivityMode;
  quality: Quality;
  autoFocus: boolean;
  live: boolean;
  panel: Panel;
  onFit: () => void;
  onBack: () => void;
  onRotate: (d: -1 | 1) => void;
  onZoom: (f: number) => void;
  onPaused: (p: boolean) => void;
  onMode: (m: ActivityMode) => void;
  onQuality: (q: Quality) => void;
  onAutoFocus: (v: boolean) => void;
  onLive: (v: boolean) => void;
  onBurst: () => void;
  onPanel: (p: Panel) => void;
}

function IconBtn({
  label,
  onClick,
  disabled,
  on,
  children,
}: Readonly<{ label: string; onClick: () => void; disabled?: boolean; on?: boolean; children: React.ReactNode }>) {
  return (
    <button
      className={`${s.btn} ${on ? s.btnOn : ""}`}
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      aria-pressed={on === undefined ? undefined : on}
      title={label}
    >
      {children}
    </button>
  );
}

export function WorldToolbar(p: Readonly<Props>) {
  return (
    <div className={`${s.card} ${s.toolbar}`} role="toolbar" aria-label="Controles del mundo">
      <IconBtn label="Filtros" on={p.panel === "filters"} onClick={() => p.onPanel(p.panel === "filters" ? null : "filters")}>
        <Filter size={16} /> Filtros
      </IconBtn>
      <IconBtn label="Actividad" on={p.panel === "feed"} onClick={() => p.onPanel(p.panel === "feed" ? null : "feed")}>
        <List size={16} /> Actividad
      </IconBtn>
      <span className={s.sep} />
      <IconBtn label="Ver todo el pueblo (Inicio)" onClick={p.onFit}>
        <Maximize size={16} />
      </IconBtn>
      <IconBtn label="Volver a la vista anterior" onClick={p.onBack} disabled={!p.canBack}>
        <Undo2 size={16} />
      </IconBtn>
      <IconBtn label="Girar a la izquierda (Q)" onClick={() => p.onRotate(-1)}>
        <RotateCcw size={16} />
      </IconBtn>
      <IconBtn label="Girar a la derecha (E)" onClick={() => p.onRotate(1)}>
        <RotateCw size={16} />
      </IconBtn>
      <IconBtn label="Acercar (+)" onClick={() => p.onZoom(0.75)}>
        <ZoomIn size={16} />
      </IconBtn>
      <IconBtn label="Alejar (-)" onClick={() => p.onZoom(1.33)}>
        <ZoomOut size={16} />
      </IconBtn>
      <span className={s.sep} />
      <IconBtn label={p.paused ? "Reanudar" : "Pausar"} on={p.paused} onClick={() => p.onPaused(!p.paused)}>
        {p.paused ? <Play size={16} /> : <Pause size={16} />}
      </IconBtn>
      <select className={s.select} value={p.mode} onChange={(e) => p.onMode(e.target.value as ActivityMode)} aria-label="Nivel de actividad">
        <option value="quiet">Silencioso</option>
        <option value="normal">Normal</option>
        <option value="busy">Mucha actividad</option>
      </select>
      <IconBtn label="Enfocar solo los eventos críticos" on={p.autoFocus} onClick={() => p.onAutoFocus(!p.autoFocus)}>
        <Crosshair size={16} /> Auto-foco
      </IconBtn>
      <span className={s.sep} />
      <IconBtn label="Eventos de demostración en vivo" on={p.live} onClick={() => p.onLive(!p.live)}>
        <Sparkles size={16} /> Demo
      </IconBtn>
      <button className={s.btn} onClick={p.onBurst} title="Lanza 25 eventos de golpe">
        Ráfaga
      </button>
      <select className={s.select} value={p.quality} onChange={(e) => p.onQuality(e.target.value as Quality)} aria-label="Calidad gráfica">
        {(Object.keys(QUALITY_LABEL) as Quality[]).map((q) => (
          <option key={q} value={q}>
            Calidad {QUALITY_LABEL[q].toLowerCase()}
          </option>
        ))}
      </select>
    </div>
  );
}
