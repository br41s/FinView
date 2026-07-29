export interface AccountValueDisplay {
  amount: number;
  kind: "market" | "cost";
}

export function getAccountValueDisplay(
  marketValue: number | null,
  cost: number | null,
): AccountValueDisplay | null {
  if (marketValue != null) return { amount: marketValue, kind: "market" };
  if (cost != null) return { amount: cost, kind: "cost" };
  return null;
}
