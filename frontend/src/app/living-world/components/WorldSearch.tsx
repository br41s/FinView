"use client";

import { Search } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { matchesQuery } from "../model/filters";
import type { WorldAsset } from "../model/types";
import s from "../world.module.css";

interface Props {
  query: string;
  assets: readonly WorldAsset[];
  onQuery: (q: string) => void;
  onPick: (a: WorldAsset) => void;
}

/**
 * Typing narrows the town live (non-matching buildings fade); choosing a result flies the
 * camera there. Name, ticker and ISIN all work, accents and case ignored.
 */
export function WorldSearch({ query, assets, onQuery, onPick }: Readonly<Props>) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const hits = useMemo(
    () => (query.trim() ? assets.filter((a) => matchesQuery(a, query)).slice(0, 7) : []),
    [assets, query],
  );

  const pick = (a: WorldAsset) => {
    setOpen(false);
    onPick(a);
  };

  return (
    <div className={s.search}>
      <Search size={16} className={s.searchIcon} aria-hidden />
      <input
        type="search"
        placeholder="Buscar empresa, ticker o ISIN"
        value={query}
        onChange={(e) => {
          onQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && hits[0]) pick(hits[0]);
          if (e.key === "Escape") setOpen(false);
        }}
        role="combobox"
        aria-expanded={open && hits.length > 0}
        aria-controls={listId}
        aria-label="Buscar en el pueblo"
      />
      {open && hits.length > 0 && (
        <div className={`${s.card} ${s.results}`} id={listId} role="listbox">
          {hits.map((a) => (
            <button key={a.id} role="option" aria-selected={false} className={s.result} onMouseDown={(e) => e.preventDefault()} onClick={() => pick(a)}>
              <span>{a.name}</span>
              <span className={s.meta}>{a.ticker ?? a.isin}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
