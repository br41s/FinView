export function formatEur(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

export function formatCurrency(
  value: string | number,
  currency: string,
): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}

export function plColor(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (n > 0) return "text-green-400";
  if (n < 0) return "text-red-400";
  return "text-neutral-400";
}

/**
 * Plain es-ES number with a fixed number of decimals; em dash for absent or
 * unparsable. Accepts strings because the fiscal API sends Decimals as text.
 */
export function fmt(n: number | string | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  const v = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(v)) return "—";
  return v.toLocaleString("es-ES", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** `v` is already in percent units (87.84 → "87.8%"); em dash for absent. */
export function fmtPct(v: number | null | undefined, decimals = 1): string {
  return v == null ? "—" : `${v.toFixed(decimals)}%`;
}

/** Compact EUR for catalogue-scale figures: €1.2B, €340.5M, €750k, €12. */
export function fmtCompact(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e9) return `€${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `€${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `€${(v / 1e3).toFixed(0)}k`;
  return `€${v.toFixed(0)}`;
}

/** ISO timestamp → es-ES date and time in the viewer's zone. */
export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("es-ES");
}
