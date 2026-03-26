const BASE = "/api";

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(
    entries.map(([k, v]) => [k, String(v)])
  ).toString();
}

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

export async function uploadIBKRReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/imports/ibkr`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export const api = {
  dashboard: (year?: number) =>
    fetchJSON(`/fiscal/dashboard${qs({ fiscal_year: year })}`),
  fiscalSummary: (year: number) => fetchJSON(`/fiscal/summary/${year}`),
  casillas: (year?: number) =>
    fetchJSON(`/fiscal/casillas${qs({ fiscal_year: year })}`),
  dividends: (year?: number) =>
    fetchJSON(`/transactions/dividends/summary${qs({ fiscal_year: year })}`),
  capitalGains: (year?: number) =>
    fetchJSON(`/transactions/capital-gains${qs({ fiscal_year: year })}`),
  transactions: (params?: Record<string, string>) => {
    const qstr = params ? "?" + new URLSearchParams(params).toString() : "";
    return fetchJSON(`/transactions/${qstr}`);
  },
  imports: () => fetchJSON("/imports/"),

  // Charts
  charts: {
    dividendsByCountry: (year?: number) =>
      fetchJSON(`/charts/dividends-by-country${qs({ fiscal_year: year })}`),
    dividendsMonthly: (year?: number) =>
      fetchJSON(`/charts/dividends-monthly${qs({ fiscal_year: year })}`),
    topDividendPayers: (year?: number, limit = 10) =>
      fetchJSON(`/charts/top-dividend-payers${qs({ limit, fiscal_year: year })}`),
    capitalGainsBreakdown: (year?: number) =>
      fetchJSON(`/charts/capital-gains-breakdown${qs({ fiscal_year: year })}`),
    patrimonioComposition: (year?: number) =>
      fetchJSON(`/charts/patrimonio-composition${qs({ fiscal_year: year })}`),
    dividendYield: (year?: number) =>
      fetchJSON(`/charts/dividend-yield${qs({ fiscal_year: year })}`),
    withholdingsByCountry: (year?: number) =>
      fetchJSON(`/charts/withholdings-by-country${qs({ fiscal_year: year })}`),
    dividendsByCompanyYearly: () =>
      fetchJSON('/charts/dividends-by-company-yearly'),
  },
};
