import { getSession } from "next-auth/react";

const BASE = "/api";

// ── Zonas Clave types ────────────────────────────────────────────────

export interface ZcWatchlistItem {
  id: number;
  ticker: string;
  name: string;
  added_at: string;
}

export interface ZcZone {
  level: number;
  zone_type: "support" | "resistance";
  strength: number;
  touches: number;
  volume_score: number;
}

export interface ZcPricePoint {
  date: string;
  close: number;
  volume: number;
}

export interface ZcAnalysis {
  id: number;
  watchlist_item_id: number;
  timestamp: string;
  zones: ZcZone[];
  trend_bias_bullish_pct: number | null;
  trend_bias_bearish_pct: number | null;
  rsi: number | null;
  macd_signal: "bullish" | "bearish" | "neutral" | null;
  macd_histogram: number | null;
  current_price: number | null;
  price_history: ZcPricePoint[];
}

export interface ZcSchedulerStatus {
  running: boolean;
  last_run: string | null;
  total_items: number;
}

// ── 5-minute client-side cache for read-heavy GET endpoints ──────────
const _memCache = new Map<string, { data: unknown; ts: number }>();
const _CACHE_TTL = 5 * 60 * 1000; // 5 min in ms

function _getCached(key: string): unknown | null {
  const entry = _memCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > _CACHE_TTL) { _memCache.delete(key); return null; }
  return entry.data;
}
function _setCached(key: string, data: unknown): void {
  _memCache.set(key, { data, ts: Date.now() });
}
export function invalidateCache(prefix?: string): void {
  if (!prefix) { _memCache.clear(); return; }
  for (const key of _memCache.keys()) {
    if (key.startsWith(prefix)) _memCache.delete(key);
  }
}

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

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
  return res.json();
}

async function fetchCached<T>(path: string): Promise<T> {
  const hit = _getCached(path);
  if (hit !== null) return hit as T;
  const data = await fetchJSON<T>(path);
  _setCached(path, data);
  return data;
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

export async function deleteAllImports() {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/all`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error(`Delete error: ${await res.text()}`);
  return res.json();
}

export async function resolveIssue(
  issueId: number,
  action: string,
  data?: Record<string, unknown>,
) {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/issues/${issueId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify({ action, data }),
  });
  if (!res.ok) throw new Error(`Error: ${await res.text()}`);
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

  // Portfolio
  portfolio: {
    positions: (skipPrices?: boolean) =>
      skipPrices
        ? fetchCached(`/portfolio/positions?skip_prices=true`)
        : fetchJSON(`/portfolio/positions`),
    summary: (skipPrices?: boolean) =>
      skipPrices
        ? fetchCached(`/portfolio/summary?skip_prices=true`)
        : fetchJSON(`/portfolio/summary`),
    positionDetail: (isin: string) =>
      fetchJSON(`/portfolio/positions/${encodeURIComponent(isin)}`),
    warmPrices: () =>
      fetchJSON("/portfolio/warm-prices", { method: "POST" }).catch(() => {}),
  },

  // Accounts
  accounts: {
    list: () => fetchJSON("/accounts/"),
    create: async (data: {
      broker: string;
      account_id: string;
      name?: string;
      currency?: string;
    }) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/accounts/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    update: async (id: number, data: { name?: string; currency?: string }) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/accounts/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    delete: async (id: number) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/accounts/${id}`, {
        method: "DELETE",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
    },
  },

  // Billing
  billing: {
    subscription: () => fetchJSON("/billing/subscription"),
    checkout: async (priceId: string) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ price_id: priceId }),
      });
      if (!res.ok) throw new Error(`Checkout error: ${await res.text()}`);
      return res.json() as Promise<{ url: string }>;
    },
    portal: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/billing/portal`, {
        method: "POST",
        headers: { ...headers },
      });
      if (!res.ok) throw new Error(`Portal error: ${await res.text()}`);
      return res.json() as Promise<{ url: string }>;
    },
  },

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

  // Options monitor
  options: {
    watchlist: () => fetchCached("/options/watchlist"),
    addToWatchlist: async (ticker: string, name = "") => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ ticker, name }),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      invalidateCache("/options/watchlist");
      return res.json();
    },
    toggleWatchlistItem: async (id: number) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/watchlist/${id}`, {
        method: "PATCH",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      invalidateCache("/options/watchlist");
      return res.json();
    },
    removeFromWatchlist: async (id: number) => {
      const headers = await authHeaders();
      await fetch(`${BASE}/options/watchlist/${id}`, {
        method: "DELETE",
        headers,
      });
      invalidateCache("/options/watchlist");
    },
    snapshots: (ticker?: string, days = 7) =>
      fetchCached(`/options/snapshots${qs({ ticker, days })}`),
    snapshotChain: (id: number) => fetchJSON(`/options/snapshots/${id}/chain`),
    tickerChain: (ticker: string) => fetchJSON(`/options/chain/${encodeURIComponent(ticker)}`),
    hiddenPortfolioTickers: () =>
      fetchCached<string[]>("/options/portfolio/hidden"),
    hidePortfolioTicker: async (ticker: string) => {
      const headers = await authHeaders();
      await fetch(`${BASE}/options/portfolio/hidden`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ ticker }),
      });
      invalidateCache("/options/portfolio/hidden");
    },
    unhidePortfolioTicker: async (ticker: string) => {
      const headers = await authHeaders();
      await fetch(`${BASE}/options/portfolio/hidden/${encodeURIComponent(ticker)}`, {
        method: "DELETE",
        headers,
      });
      invalidateCache("/options/portfolio/hidden");
    },
    checkAvailability: async (tickers: string[]) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/check-availability`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ tickers }),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<{ has_options: string[]; no_options: string[] }>;
    },
    alerts: (ticker?: string, unread?: boolean, days = 7) =>
      fetchJSON(
        `/options/alerts${qs({
          ticker,
          unread: unread ? "true" : undefined,
          days,
        })}`,
      ),
    ackAlert: async (id: number) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/alerts/${id}/ack`, {
        method: "PATCH",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    ackAllAlerts: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/alerts/ack-all`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    unusual: (ticker?: string, days = 7) =>
      fetchJSON(`/options/unusual${qs({ ticker, days })}`),
    agentStatus: () => fetchJSON("/options/agent/status"),
    runCycle: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/agent/run`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    startAgent: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/agent/start`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    stopAgent: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/agent/stop`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    backtestSignals: (params?: { ticker?: string; days?: number }) =>
      fetchJSON(`/options/backtest${qs(params ?? {})}`),
    backtestStats: (ticker?: string) =>
      fetchJSON(`/options/backtest/stats${ticker ? qs({ ticker }) : ""}`),
    backtestEvaluate: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/backtest/evaluate`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    ask: async (question: string, history: { role: string; content: string }[] = []) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ question, history }),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<{ answer: string }>;
    },
  },

  // Zonas Clave
  zonasClav: {
    watchlist: () => fetchJSON<ZcWatchlistItem[]>("/zonas-clave/watchlist"),

    addTicker: async (ticker: string, name = "") => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/zonas-clave/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ ticker, name }),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<ZcWatchlistItem>;
    },

    removeTicker: async (id: number) => {
      const headers = await authHeaders();
      await fetch(`${BASE}/zonas-clave/watchlist/${id}`, {
        method: "DELETE",
        headers,
      });
    },

    analysis: (ticker: string) =>
      fetchJSON<ZcAnalysis>(`/zonas-clave/analysis/${encodeURIComponent(ticker)}`),

    allAnalyses: () => fetchJSON<ZcAnalysis[]>("/zonas-clave/analysis"),

    triggerAnalysis: async (ticker: string) => {
      const headers = await authHeaders();
      const res = await fetch(
        `${BASE}/zonas-clave/analyze/${encodeURIComponent(ticker)}`,
        { method: "POST", headers },
      );
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<ZcAnalysis>;
    },

    triggerAll: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/zonas-clave/analyze-all`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },

    schedulerStatus: () =>
      fetchJSON<ZcSchedulerStatus>("/zonas-clave/scheduler/status"),

    startScheduler: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/zonas-clave/scheduler/start`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },

    stopScheduler: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/zonas-clave/scheduler/stop`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
  },
};
