"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";

/**
 * The Zonas (técnico) lens as seen from the options watchlist: which tickers
 * already have a Zonas Clave row, and which are mid-toggle.
 *
 * Lifted out of OptionsPage unchanged. It owns nothing the rest of the page
 * writes to — the lens map loads best-effort on mount and is re-fetched after
 * each toggle — so it is the one piece of page state that comes out clean.
 */
export interface CrossLens {
  /** ticker → zonas item id, for tickers on the Zonas Clave watchlist. */
  zonasMap: Map<string, number>;
  zonasBusy: Set<string>;
  toggleZonasLens: (ticker: string, name: string) => Promise<void>;
}

export function useCrossLens(): CrossLens {
  // Zonas (técnico) lens state for cross-section toggles: ticker → zonas item id
  const [zonasMap, setZonasMap] = useState<Map<string, number>>(new Map());
  const [zonasBusy, setZonasBusy] = useState<Set<string>>(new Set());

  // Zonas lens info for the watchlist's "Técnico" toggles — best-effort
  useEffect(() => {
    api.zonasClav
      .watchlist()
      .then((items) => setZonasMap(new Map(items.map((i) => [i.ticker, i.id]))))
      .catch(bestEffort("zonas lens map for the watchlist"));
  }, []);

  // ── Zonas (técnico) lens — cross-section toggle from the watchlist ──
  async function toggleZonasLens(ticker: string, name: string) {
    if (zonasBusy.has(ticker)) return;
    setZonasBusy((prev) => new Set(prev).add(ticker));
    try {
      const id = zonasMap.get(ticker);
      if (id != null) {
        await api.zonasClav.removeTicker(id);
      } else {
        // Same semantics as adding from /zonas-clave: fires the S/R analysis.
        await api.zonasClav.addTicker(ticker, name);
      }
      const items = await api.zonasClav.watchlist();
      setZonasMap(new Map(items.map((i) => [i.ticker, i.id])));
    } catch (e) {
      console.error("zonas lens toggle:", e);
    } finally {
      setZonasBusy((prev) => {
        const next = new Set(prev);
        next.delete(ticker);
        return next;
      });
    }
  }

  return { zonasMap, zonasBusy, toggleZonasLens };
}
