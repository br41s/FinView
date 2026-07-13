"use client";

import { useEffect, useState } from "react";

import { api, type OhlcBar } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { CHART_SCOPES, SCOPE_PARAMS, type ChartScope } from "@/lib/chartMarkers";
import { Skeleton } from "@/components/ui/skeleton";

export function PrecioTab({ symbol }: { symbol: string }) {
  const [bars, setBars] = useState<OhlcBar[] | null>(null);
  const [scope, setScope] = useState<ChartScope>("1A");

  useEffect(() => {
    let cancelled = false;
    setBars(null);
    const { period, interval } = SCOPE_PARAMS[scope];
    api.charts
      .priceHistory(symbol, period, interval)
      .then((b) => {
        if (!cancelled) setBars(b);
      })
      .catch(() => {
        if (!cancelled) setBars([]);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, scope]);

  if (bars === null) return <Skeleton className="h-[360px] w-full" />;
  if (bars.length === 0) {
    return (
      <div className="flex h-[360px] items-center justify-center text-sm text-muted-foreground">
        Sin datos de precio para {symbol}.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-0.5">
        {CHART_SCOPES.map((s) => (
          <button
            key={s}
            onClick={() => setScope(s)}
            className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
              scope === s
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            {s}
          </button>
        ))}
      </div>
      <PriceChart data={bars} height={360} />
    </div>
  );
}
