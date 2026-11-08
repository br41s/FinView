"use client";

import { X } from "lucide-react";
import { ARCHETYPE_LABEL } from "../model/archetypes";
import { hasActiveFilters } from "../model/filters";
import {
  ARCHETYPES,
  type AssetType,
  type Direction,
  type EventCategory,
  type Severity,
  type WorldAsset,
  type WorldFilters,
} from "../model/types";
import s from "../world.module.css";
import { ASSET_TYPE_LABEL, CATEGORY_LABEL, DIRECTION_LABEL, SEVERITY_LABEL } from "./labels";

type Toggle = <K extends "assetTypes" | "archetypes" | "countries" | "brokers" | "directions" | "categories" | "severities">(
  key: K,
  value: WorldFilters[K][number],
) => void;

function Chips<T extends string>({
  options,
  selected,
  onToggle,
}: Readonly<{ options: ReadonlyArray<readonly [T, string]>; selected: readonly T[]; onToggle: (v: T) => void }>) {
  return (
    <div className={s.wrap}>
      {options.map(([v, label]) => (
        <button
          key={v}
          className={`${s.chip} ${selected.includes(v) ? s.chipOn : ""}`}
          aria-pressed={selected.includes(v)}
          onClick={() => onToggle(v)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

const entries = <T extends string>(r: Record<T, string>, keys?: readonly T[]) =>
  (keys ?? (Object.keys(r) as T[])).map((k) => [k, r[k]] as const);

interface Props {
  filters: WorldFilters;
  assets: readonly WorldAsset[];
  onSet: (p: Partial<WorldFilters>) => void;
  onToggle: Toggle;
  onClear: () => void;
}

export function WorldFiltersPanel({ filters: f, assets, onSet, onToggle, onClear }: Readonly<Props>) {
  const countries = [...new Set(assets.map((a) => a.country).filter((c): c is string => !!c))].sort();
  const brokers = [...new Set(assets.flatMap((a) => a.brokers))].sort();
  const assetTypes: AssetType[] = ["equity", "etf", "cash", "crypto"];
  const sevs: Severity[] = ["normal", "important", "critical"];
  const dirs: Direction[] = ["positive", "negative", "neutral"];
  const cats: EventCategory[] = ["market", "corporate", "portfolio", "technical", "options"];

  return (
    <section className={`${s.card} ${s.panel}`} aria-label="Filtros">
      <div className={s.panelHead}>
        <span>Filtros</span>
        <button className={s.btn} onClick={onClear} disabled={!hasActiveFilters(f)}>
          Limpiar
        </button>
      </div>
      <div className={s.panelBody}>
        <div className={s.group}>
          <p className={s.groupTitle}>Peso en cartera</p>
          <select
            className={s.select}
            value={f.minWeightPct ?? ""}
            onChange={(e) => onSet({ minWeightPct: e.target.value === "" ? null : Number(e.target.value) })}
            aria-label="Peso mínimo"
          >
            <option value="">Todas las posiciones</option>
            <option value="1">Desde 1 %</option>
            <option value="3">Desde 3 %</option>
            <option value="5">Desde 5 %</option>
          </select>
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Tipo de activo</p>
          <Chips options={entries(ASSET_TYPE_LABEL, assetTypes)} selected={f.assetTypes} onToggle={(v) => onToggle("assetTypes", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Sector</p>
          <Chips options={entries(ARCHETYPE_LABEL, ARCHETYPES)} selected={f.archetypes} onToggle={(v) => onToggle("archetypes", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>País</p>
          <Chips options={countries.map((c) => [c, c] as const)} selected={f.countries} onToggle={(v) => onToggle("countries", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Cuenta o bróker</p>
          <Chips options={brokers.map((c) => [c, c] as const)} selected={f.brokers} onToggle={(v) => onToggle("brokers", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Dirección</p>
          <Chips options={entries(DIRECTION_LABEL, dirs)} selected={f.directions} onToggle={(v) => onToggle("directions", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Categoría de evento</p>
          <Chips options={entries(CATEGORY_LABEL, cats)} selected={f.categories} onToggle={(v) => onToggle("categories", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Severidad</p>
          <Chips options={entries(SEVERITY_LABEL, sevs)} selected={f.severities} onToggle={(v) => onToggle("severities", v)} />
        </div>
        <div className={s.group}>
          <p className={s.groupTitle}>Vista</p>
          <div className={s.wrap}>
            <button className={`${s.chip} ${f.favouritesOnly ? s.chipOn : ""}`} aria-pressed={f.favouritesOnly} onClick={() => onSet({ favouritesOnly: !f.favouritesOnly })}>
              Favoritos
            </button>
            <button className={`${s.chip} ${f.activeOnly ? s.chipOn : ""}`} aria-pressed={f.activeOnly} onClick={() => onSet({ activeOnly: !f.activeOnly })}>
              Solo con actividad
            </button>
            <button className={`${s.chip} ${f.isolate ? s.chipOn : ""}`} aria-pressed={f.isolate} onClick={() => onSet({ isolate: !f.isolate })}>
              Aislar resultados
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

/** One removable chip per active restriction, so nothing narrows the town invisibly. */
export function ActiveFilterChips({
  filters: f,
  onSet,
  onToggle,
}: Readonly<{ filters: WorldFilters; onSet: (p: Partial<WorldFilters>) => void; onToggle: Toggle }>) {
  const chips: Array<{ key: string; label: string; remove: () => void }> = [];
  if (f.query.trim()) chips.push({ key: "q", label: `«${f.query.trim()}»`, remove: () => onSet({ query: "" }) });
  if (f.minWeightPct !== null) chips.push({ key: "w", label: `Peso ≥ ${f.minWeightPct} %`, remove: () => onSet({ minWeightPct: null }) });
  f.assetTypes.forEach((v) => chips.push({ key: `t${v}`, label: ASSET_TYPE_LABEL[v], remove: () => onToggle("assetTypes", v) }));
  f.archetypes.forEach((v) => chips.push({ key: `a${v}`, label: ARCHETYPE_LABEL[v], remove: () => onToggle("archetypes", v) }));
  f.countries.forEach((v) => chips.push({ key: `c${v}`, label: v, remove: () => onToggle("countries", v) }));
  f.brokers.forEach((v) => chips.push({ key: `b${v}`, label: v, remove: () => onToggle("brokers", v) }));
  f.directions.forEach((v) => chips.push({ key: `d${v}`, label: DIRECTION_LABEL[v], remove: () => onToggle("directions", v) }));
  f.categories.forEach((v) => chips.push({ key: `k${v}`, label: CATEGORY_LABEL[v], remove: () => onToggle("categories", v) }));
  f.severities.forEach((v) => chips.push({ key: `s${v}`, label: SEVERITY_LABEL[v], remove: () => onToggle("severities", v) }));
  if (f.favouritesOnly) chips.push({ key: "fav", label: "Favoritos", remove: () => onSet({ favouritesOnly: false }) });
  if (f.activeOnly) chips.push({ key: "act", label: "Solo con actividad", remove: () => onSet({ activeOnly: false }) });
  if (chips.length === 0) return null;
  return (
    <div className={s.chips} role="list" aria-label="Filtros activos">
      {chips.map((c) => (
        <button key={c.key} role="listitem" className={`${s.chip} ${s.chipOn}`} onClick={c.remove} aria-label={`Quitar filtro ${c.label}`}>
          {c.label} <X size={12} />
        </button>
      ))}
    </div>
  );
}
