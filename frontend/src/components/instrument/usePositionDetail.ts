"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export interface InstrumentDetail {
  isin: string;
  name: string;
  ticker: string | null;
  country: string | null;
  total_quantity: number;
  avg_cost_eur: number | null;
  total_cost_eur: number | null;
  current_price_eur: number | null;
  market_value_eur: number | null;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  accounts: {
    broker: string;
    account_id: string;
    quantity: number;
    cost_eur: number | null;
    value_eur: number | null;
  }[];
  dividends_by_year: { year: number; gross_eur: number; net_eur: number; count: number }[];
  dividend_events: { date: string; net_eur: number }[];
}

export type PositionDetailState = {
  status: "loading" | "ok" | "absent";
  detail: InstrumentDetail | null;
};

// Session cache keyed by ISIN so the Fiscal and Dividendos tabs share one fetch.
// Successes are cached; failures (404 = no open position) are not, so they can retry.
const cache = new Map<string, Promise<InstrumentDetail>>();

export function usePositionDetail(isin: string | null): PositionDetailState {
  const [state, setState] = useState<PositionDetailState>({ status: "loading", detail: null });

  useEffect(() => {
    if (!isin) {
      setState({ status: "absent", detail: null });
      return;
    }
    let cancelled = false;
    setState({ status: "loading", detail: null });

    let p = cache.get(isin);
    if (!p) {
      p = api.portfolio.positionDetail(isin) as Promise<InstrumentDetail>;
      cache.set(isin, p);
    }
    p.then((d) => {
      if (!cancelled) setState({ status: "ok", detail: d });
    }).catch(() => {
      cache.delete(isin); // 404 / error — allow a later retry
      if (!cancelled) setState({ status: "absent", detail: null });
    });

    return () => {
      cancelled = true;
    };
  }, [isin]);

  return state;
}
