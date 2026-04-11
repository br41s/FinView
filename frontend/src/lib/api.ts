import { getSession } from "next-auth/react";

const BASE = "/api";

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return "";
  return (
    "?" +
    new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString()
  );
}

async function authHeaders(): Promise<HeadersInit> {
  const session = await getSession();
  if (session?.accessToken) {
    return { Authorization: `Bearer ${session.accessToken}` };
  }
  return {};
}

async function fetchJSON<T>(path: string): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", headers });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function uploadTRReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/tr`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function uploadDGReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/degiro`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function uploadIBKRReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/ibkr`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function uploadINGReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/ing`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function uploadBBVAReport(files: File[]) {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/bbva`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function uploadEToroReport(file: File) {
  const form = new FormData();
  form.append("file", file);
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/etoro`, {
    method: "POST",
    body: form,
    headers,
  });
  if (!res.ok) throw new Error(`Import error: ${await res.text()}`);
  return res.json();
}

export async function deleteImport(importId: number) {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/${importId}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error(`Delete error: ${await res.text()}`);
  return res.json();
}

export const api = {
  dashboard: (year?: number) =>
    fetchJSON(`/fiscal/dashboard${qs({ fiscal_year: year })}`),
  fiscalSummary: (year: number) => fetchJSON(`/fiscal/summary/${year}`),
  casillas: (year?: number) =>
    fetchJSON(`/fiscal/casillas${qs({ fiscal_year: year })}`),
  exportFiscal: async (year: number, format: "json" | "csv" = "json") => {
    const headers = await authHeaders();
    const res = await fetch(`${BASE}/fiscal/export/${year}?format=${format}`, {
      cache: "no-store",
      headers,
    });
    if (!res.ok) throw new Error(`Export error: ${await res.text()}`);
    if (format === "csv") {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `finview_casillas_${year}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      return null;
    }
    return res.json();
  },
  dividends: (year?: number) =>
    fetchJSON(`/transactions/dividends/summary${qs({ fiscal_year: year })}`),
  capitalGains: (year?: number) =>
    fetchJSON(`/transactions/capital-gains${qs({ fiscal_year: year })}`),
  crossBrokerLots: (year: number) =>
    fetchJSON(`/fiscal/cross-broker-lots${qs({ fiscal_year: year })}`),
  fifoAdjustments: (year: number) =>
    fetchJSON(`/fiscal/fifo-adjustments${qs({ fiscal_year: year })}`),
  optionAssignments: (year: number) =>
    fetchJSON(`/fiscal/option-assignments${qs({ fiscal_year: year })}`),
  crossValidation: (year: number) =>
    fetchJSON(`/fiscal/cross-validation/${year}`),
  yearlyComparison: () => fetchJSON("/fiscal/yearly-comparison"),
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
      fetchJSON(
        `/charts/top-dividend-payers${qs({ limit, fiscal_year: year })}`,
      ),
    capitalGainsBreakdown: (year?: number) =>
      fetchJSON(`/charts/capital-gains-breakdown${qs({ fiscal_year: year })}`),
    patrimonioComposition: (year?: number) =>
      fetchJSON(`/charts/patrimonio-composition${qs({ fiscal_year: year })}`),
    dividendYield: (year?: number) =>
      fetchJSON(`/charts/dividend-yield${qs({ fiscal_year: year })}`),
    withholdingsByCountry: (year?: number) =>
      fetchJSON(`/charts/withholdings-by-country${qs({ fiscal_year: year })}`),
    dividendsByCompanyYearly: () =>
      fetchJSON("/charts/dividends-by-company-yearly"),
  },
};
