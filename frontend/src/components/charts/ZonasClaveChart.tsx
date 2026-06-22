"use client";

import { PriceChart, type PriceLine } from "@/components/charts/PriceChart";
import type { ZcPricePoint, ZcZone } from "@/lib/api";

// Thin wrapper: maps support/resistance zones to PriceChart price-lines.
export function ZonasClaveChart({
  data,
  zones,
}: Readonly<{ data: ZcPricePoint[]; zones: ZcZone[] }>) {
  const priceLines: PriceLine[] = zones.map((z) => ({
    price: z.level,
    color: z.zone_type === "support" ? "#22c55e" : "#ef4444",
    strength: z.strength,
    title: z.level.toFixed(2),
  }));

  return <PriceChart data={data} priceLines={priceLines} />;
}
