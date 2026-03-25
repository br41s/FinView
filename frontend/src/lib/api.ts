const BASE = "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function uploadTRReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/imports/tr`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function uploadDGReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/imports/degiro`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export const api = {
  dashboard: () => fetchJSON("/fiscal/dashboard"),
  fiscalSummary: (year: number) => fetchJSON(`/fiscal/summary/${year}`),
  casillas: (year?: number) =>
    fetchJSON(`/fiscal/casillas${year ? `?fiscal_year=${year}` : ""}`),
  dividends: (year?: number) =>
    fetchJSON(`/transactions/dividends/summary${year ? `?fiscal_year=${year}` : ""}`),
  capitalGains: (year?: number) =>
    fetchJSON(`/transactions/capital-gains${year ? `?fiscal_year=${year}` : ""}`),
  transactions: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return fetchJSON(`/transactions/${qs}`);
  },
  imports: () => fetchJSON("/imports/"),

  // Charts
  charts: {
    dividendsByCountry: (year?: number) =>
      fetchJSON(`/charts/dividends-by-country${year ? `?fiscal_year=${year}` : ""}`),
    dividendsMonthly: (year?: number) =>
      fetchJSON(`/charts/dividends-monthly${year ? `?fiscal_year=${year}` : ""}`),
    topDividendPayers: (year?: number, limit = 10) =>
      fetchJSON(`/charts/top-dividend-payers?limit=${limit}${year ? `&fiscal_year=${year}` : ""}`),
    capitalGainsBreakdown: (year?: number) =>
      fetchJSON(`/charts/capital-gains-breakdown${year ? `?fiscal_year=${year}` : ""}`),
    patrimonioComposition: () => fetchJSON("/charts/patrimonio-composition"),
    dividendYield: (year?: number) =>
      fetchJSON(`/charts/dividend-yield${year ? `?fiscal_year=${year}` : ""}`),
    withholdingsByCountry: (year?: number) =>
      fetchJSON(`/charts/withholdings-by-country${year ? `?fiscal_year=${year}` : ""}`),
  },
};
