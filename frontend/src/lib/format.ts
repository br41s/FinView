export function formatEur(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency: "EUR",
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
