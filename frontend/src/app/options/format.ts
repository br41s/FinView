/**
 * Number formatting for the options page: es-ES digits, em dash for absent.
 *
 * Distinct from lib/format.ts, which formats currency. Lives here because
 * both page.tsx and the extracted tabs need it.
 */
export function fmt(n: number | string | null | undefined, d = 2): string {
  if (n == null) return "—";
  const v = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(v)) return "—";
  return v.toLocaleString("es-ES", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}
