"use client";

import { useCallback, useEffect, useState } from "react";

import { api, type OhlcBar } from "@/lib/api";
import { SCOPE_PARAMS, type ChartScope } from "@/lib/chartMarkers";

import type { PositionDetail } from "./types";

/**
 * Row-expansion state for the positions list, lifted out of PortfolioContent.
 *
 * One row is expanded at a time; its detail is fetched once and cached by
 * ISIN. The OHLC series for the price chart is cached per `isin:scope`, so
 * switching scope or re-expanding does not refetch, and a failed fetch is
 * stored as `[]` (which hides the chart) rather than retried.
 */
export interface PositionDetails {
  expandedIsin: string | null;
  details: Map<string, PositionDetail>;
  loadingDetail: string | null;
  handleExpand: (isin: string) => Promise<void>;
  ohlcByIsin: Map<string, OhlcBar[]>;
  chartScope: ChartScope;
  setChartScope: (scope: ChartScope) => void;
}

export function usePositionDetails(): PositionDetails {
  const [expandedIsin, setExpandedIsin] = useState<string | null>(null);
  const [ohlcByIsin, setOhlcByIsin] = useState<Map<string, OhlcBar[]>>(new Map());
  const [chartScope, setChartScope] = useState<ChartScope>("MAX");
  const [details, setDetails] = useState<Map<string, PositionDetail>>(
    new Map(),
  );
  const [loadingDetail, setLoadingDetail] = useState<string | null>(null);

  const handleExpand = useCallback(
    async (isin: string) => {
      if (expandedIsin === isin) {
        setExpandedIsin(null);
        return;
      }
      setExpandedIsin(isin);
      if (!details.has(isin)) {
        setLoadingDetail(isin);
        try {
          const data = (await api.portfolio.positionDetail(
            isin,
          )) as PositionDetail;
          setDetails((prev) => new Map(prev).set(isin, data));
        } catch (e) {
          console.error("Failed to load detail:", e);
        } finally {
          setLoadingDetail(null);
        }
      }
    },
    [expandedIsin, details],
  );

  // Fetch OHLC for the expanded position + selected scope. Cached per
  // "isin:scope" so switching scope/re-expanding doesn't refetch. Best-effort
  // → empty hides the chart.
  useEffect(() => {
    if (!expandedIsin) return;
    const detail = details.get(expandedIsin);
    const cacheKey = `${expandedIsin}:${chartScope}`;
    if (!detail?.ticker || ohlcByIsin.has(cacheKey)) return;
    const { period, interval } = SCOPE_PARAMS[chartScope];
    api.charts
      .priceHistory(detail.ticker, period, interval)
      .then((bars) =>
        setOhlcByIsin((prev) => new Map(prev).set(cacheKey, bars)),
      )
      .catch(() =>
        setOhlcByIsin((prev) => new Map(prev).set(cacheKey, [])),
      );
  }, [expandedIsin, chartScope, details, ohlcByIsin]);

  return {
    expandedIsin,
    details,
    loadingDetail,
    handleExpand,
    ohlcByIsin,
    chartScope,
    setChartScope,
  };
}
