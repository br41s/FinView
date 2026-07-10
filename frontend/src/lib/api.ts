import { getSession } from "next-auth/react";

import type { GeoSignal } from "@/lib/geo";
import type { SavingsEstimate } from "@/lib/types";

const BASE = "/api";

export interface GeoSchedulerStatus {
  running: boolean;
  interval_minutes: number;
  total_signals: number;
  active_signals: number;
  last_signal_at: string | null;
}

// ── Markets types ────────────────────────────────────────────────────

export interface MarketsWatchlistItem {
  id: number;
  ticker: string;
  name: string;
  created_at: string;
}

export interface TickerAnalysis {
  status: string;
  ticker: string;
  summary: {
    current_price: number | null;
    put_call_ratio_volume: number | null;
    put_call_ratio_oi: number | null;
    avg_call_iv: number | null;
    avg_put_iv: number | null;
    historical_volatility: number | null;
    iv_skew: number | null;
    market_sentiment: string | null;
  };
  alerts: { type?: string; severity?: string; message?: string }[];
  unusual: { type?: string; ticker?: string; detail?: string }[];
  analysis: string | null;
  ai_configured: boolean;
  ai_error: string | null;
}

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
  // OHLC added for candlestick rendering; optional so analyses stored before this
  // change (close-only) still parse and fall back to a line series.
  open?: number;
  high?: number;
  low?: number;
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

export interface OhlcBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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

// ── Access-token cache ───────────────────────────────────────────────
// getSession() hits /api/auth/session over the network on every call. The
// dashboard fires ~16 requests on load, so calling it per-request added ~16
// extra round-trips on the critical path. The accessToken is a long-lived JWT
// that only changes on login/logout, so we resolve it once and reuse it until
// it nears expiry (decoded from the JWT) or a request comes back 401.
let _cachedToken: string | null = null;
let _tokenExp = 0; // epoch seconds; 0 = unknown
let _tokenPromise: Promise<string | null> | null = null;

function _decodeExp(token: string): number {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.exp === "number" ? payload.exp : 0;
  } catch {
    return 0;
  }
}

export function clearAuthToken(): void {
  _cachedToken = null;
  _tokenExp = 0;
  _tokenPromise = null;
}

async function _resolveToken(): Promise<string | null> {
  const now = Date.now() / 1000;
  // Reuse cached token while it has >60s of life (exp unknown ⇒ treat as valid).
  if (_cachedToken && (_tokenExp === 0 || _tokenExp - now > 60)) {
    return _cachedToken;
  }
  // Dedupe concurrent resolves (16 parallel requests ⇒ a single getSession()).
  if (_tokenPromise) return _tokenPromise;
  _tokenPromise = getSession()
    .then((session) => {
      const token = session?.accessToken ?? null;
      _cachedToken = token;
      _tokenExp = token ? _decodeExp(token) : 0;
      return token;
    })
    .finally(() => {
      _tokenPromise = null;
    });
  return _tokenPromise;
}

async function authHeaders(): Promise<HeadersInit> {
  const token = await _resolveToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function fetchJSON<T>(
  path: string,
  init?: RequestInit,
  _retried = false,
): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  });
  // A 401 means the cached token is stale (rotated/expired/logged out elsewhere).
  // Drop it and retry once with a freshly-resolved token.
  if (res.status === 401 && !_retried) {
    clearAuthToken();
    return fetchJSON<T>(path, init, true);
  }
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
  invalidateCache();
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
  invalidateCache();
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
  invalidateCache();
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
  invalidateCache();
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
  invalidateCache();
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
  invalidateCache();
  return res.json();
}

export async function deleteImport(importId: number) {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/${importId}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error(`Delete error: ${await res.text()}`);
  invalidateCache();
  return res.json();
}

export async function deleteAllImports() {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}/imports/all`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) throw new Error(`Delete error: ${await res.text()}`);
  invalidateCache();
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
  invalidateCache();
  return res.json();
}

// ── Alternative Investments types ────────────────────────────────────

export type AltInvestmentType =
  | "PRIVATE_EQUITY"
  | "VENTURE_CAPITAL"
  | "REAL_ESTATE"
  | "HEDGE_FUND"
  | "STRUCTURED_PRODUCT"
  | "OTHER";

export type AltInvestmentStatus = "ACTIVE" | "REALIZED";

export interface AltInvestment {
  id: number;
  name: string;
  type: AltInvestmentType;
  status: AltInvestmentStatus;
  manager: string;
  isin: string | null;
  vintage_year: number | null;
  geography: string;
  currency: string;
  committed_capital: number;
  called_capital: number;
  distributed_capital: number;
  current_nav: number;
  notes: string;
  unfunded: number;
  total_value: number;
  tvpi: number | null;
  dpi: number | null;
  rvpi: number | null;
}

export interface AltInvestmentInput {
  name: string;
  type: AltInvestmentType;
  status?: AltInvestmentStatus;
  manager?: string;
  isin?: string | null;
  vintage_year?: number | null;
  geography?: string;
  currency?: string;
  committed_capital?: number;
  called_capital?: number;
  distributed_capital?: number;
  current_nav?: number;
  notes?: string;
}

export interface AltAllocationSlice {
  label: string;
  value: number;
  pct: number;
}

export interface AltCatalogResult {
  name: string;
  type: AltInvestmentType;
  manager: string;
  isin: string | null;
  source: string;
  nav: number | null;
  fund_size: number | null;
  data_date: string | null;
}

export type AltCatalogSort = "name" | "fund_size_desc" | "nav_desc" | "nav_asc";

export interface AltCatalogQuery {
  q?: string;
  type?: AltInvestmentType;
  min_fund_size?: number;
  sort?: AltCatalogSort;
}

export interface AltSummary {
  count: number;
  total_committed: number;
  total_called: number;
  total_distributed: number;
  total_nav: number;
  total_unfunded: number;
  total_value: number;
  overall_tvpi: number | null;
  overall_dpi: number | null;
  overall_rvpi: number | null;
  by_type: AltAllocationSlice[];
  by_geography: AltAllocationSlice[];
  by_currency: AltAllocationSlice[];
}

export const api = {
  dashboard: (year?: number) =>
    fetchCached(`/fiscal/dashboard${qs({ fiscal_year: year })}`),
  fiscalSummary: (year: number) => fetchCached(`/fiscal/summary/${year}`),
  casillas: (year?: number) =>
    fetchCached(`/fiscal/casillas${qs({ fiscal_year: year })}`),
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
    fetchCached(`/transactions/dividends/summary${qs({ fiscal_year: year })}`),
  capitalGains: (year?: number) =>
    fetchCached(`/transactions/capital-gains${qs({ fiscal_year: year })}`),
  crossBrokerLots: (year: number) =>
    fetchCached(`/fiscal/cross-broker-lots${qs({ fiscal_year: year })}`),
  fifoAdjustments: (year: number) =>
    fetchCached(`/fiscal/fifo-adjustments${qs({ fiscal_year: year })}`),
  optionAssignments: (year: number) =>
    fetchCached(`/fiscal/option-assignments${qs({ fiscal_year: year })}`),
  crossValidation: (year: number) =>
    fetchCached(`/fiscal/cross-validation/${year}`),
  yearlyComparison: () => fetchCached("/fiscal/yearly-comparison"),

  // Fiscal onboarding — savings-base estimate (v1 individual)
  fiscalProfile: (year: number) => fetchJSON(`/fiscal/profile/${year}`),
  saveFiscalProfile: async (
    year: number,
    body: {
      age: number | null;
      disability: "general" | "severe" | null;
      descendants: number;
      general_base: string;
    },
  ) => {
    const headers = await authHeaders();
    const res = await fetch(`${BASE}/fiscal/profile/${year}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Error: ${await res.text()}`);
    invalidateCache(`/fiscal/estimate/${year}`);
    return res.json();
  },
  manualIncome: (year: number) => fetchJSON(`/fiscal/manual-income/${year}`),
  addManualIncome: async (body: {
    fiscal_year: number;
    category: "RCM" | "GAIN" | "LOSS";
    label: string;
    amount_eur: string;
    withholding_eur: string;
  }) => {
    const headers = await authHeaders();
    const res = await fetch(`${BASE}/fiscal/manual-income`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Error: ${await res.text()}`);
    invalidateCache(`/fiscal/estimate/${body.fiscal_year}`);
    return res.json();
  },
  deleteManualIncome: async (id: number, year: number) => {
    const headers = await authHeaders();
    await fetch(`${BASE}/fiscal/manual-income/${id}`, {
      method: "DELETE",
      headers,
    });
    invalidateCache(`/fiscal/estimate/${year}`);
  },
  savingsEstimate: (year: number): Promise<SavingsEstimate> =>
    fetchCached(`/fiscal/estimate/${year}`),
  exportSavingsEstimate: async (year: number) => {
    const headers = await authHeaders();
    const res = await fetch(`${BASE}/fiscal/estimate/${year}/export?format=csv`, {
      cache: "no-store",
      headers,
    });
    if (!res.ok) throw new Error(`Export error: ${await res.text()}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `finview_estimacion_ahorro_${year}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },
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

  // Charts — cached client-side (5 min); invalidated on import/delete.
  charts: {
    dividendsByCountry: (year?: number) =>
      fetchCached(`/charts/dividends-by-country${qs({ fiscal_year: year })}`),
    dividendsMonthly: (year?: number) =>
      fetchCached(`/charts/dividends-monthly${qs({ fiscal_year: year })}`),
    topDividendPayers: (year?: number, limit = 10) =>
      fetchCached(
        `/charts/top-dividend-payers${qs({ limit, fiscal_year: year })}`,
      ),
    capitalGainsBreakdown: (year?: number) =>
      fetchCached(`/charts/capital-gains-breakdown${qs({ fiscal_year: year })}`),
    patrimonioComposition: (year?: number) =>
      fetchCached(`/charts/patrimonio-composition${qs({ fiscal_year: year })}`),
    dividendYield: (year?: number) =>
      fetchCached(`/charts/dividend-yield${qs({ fiscal_year: year })}`),
    withholdingsByCountry: (year?: number) =>
      fetchCached(`/charts/withholdings-by-country${qs({ fiscal_year: year })}`),
    dividendsByCompanyYearly: () =>
      fetchCached("/charts/dividends-by-company-yearly"),
    priceHistory: (ticker: string, period = "2y") =>
      fetchJSON<OhlcBar[]>(`/charts/price-history${qs({ ticker, period })}`),
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
    tickerChain: (ticker: string, expiration?: string) =>
      fetchJSON(`/options/chain/${encodeURIComponent(ticker)}${expiration ? `?expiration=${encodeURIComponent(expiration)}` : ""}`),
    tickerExpirations: (ticker: string) =>
      fetchJSON(`/options/expirations/${encodeURIComponent(ticker)}`),
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
    lastAnalysis: () =>
      fetchJSON<{
        timestamp: string | null;
        cycle: number | null;
        tickers_analyzed: number | null;
        alerts: number | null;
        unusual: number | null;
        market_sentiment: string | null;
        claude_analysis: string | null;
        ai_configured: boolean;
        macro: {
          regime: string;
          vix: number | null;
          yield_spread: number | null;
          financial_stress: number | null;
          hy_spread: number | null;
          as_of: string | null;
        } | null;
      }>("/options/agent/last-analysis"),
    runCycle: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/agent/run`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    analyzeTicker: async (ticker: string) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/options/agent/analyze-ticker`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ ticker }),
      });
      if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
      return res.json() as Promise<TickerAnalysis>;
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

  // Markets — DB-backed candlestick-viewer watchlist
  markets: {
    watchlist: () => fetchJSON<MarketsWatchlistItem[]>("/markets/watchlist"),
    addTicker: async (ticker: string, name = "") => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/markets/watchlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ ticker, name }),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<MarketsWatchlistItem>;
    },
    importTickers: async (tickers: string[]) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/markets/watchlist/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ tickers }),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<MarketsWatchlistItem[]>;
    },
    removeTicker: async (id: number) => {
      const headers = await authHeaders();
      await fetch(`${BASE}/markets/watchlist/${id}`, {
        method: "DELETE",
        headers,
      });
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

  // Geo-Intel
  geo: {
    signals: (status: "active" | "resolved" | "all" = "active") =>
      fetchJSON<GeoSignal[]>(`/geo/signals?status=${status}`),
    run: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/geo/run`, { method: "POST", headers });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    schedulerStatus: () =>
      fetchJSON<GeoSchedulerStatus>("/geo/scheduler/status"),
    startScheduler: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/geo/scheduler/start`, { method: "POST", headers });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
    stopScheduler: async () => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/geo/scheduler/stop`, { method: "POST", headers });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json();
    },
  },

  // Alternative investments (private banking)
  altInvestments: {
    list: () => fetchJSON<AltInvestment[]>("/alt-investments/"),
    summary: () => fetchJSON<AltSummary>("/alt-investments/summary"),
    search: (params: AltCatalogQuery) =>
      fetchJSON<AltCatalogResult[]>(
        `/alt-investments/search${qs({
          q: params.q,
          type: params.type,
          min_fund_size: params.min_fund_size,
          sort: params.sort,
          limit: 20,
        })}`,
      ),
    create: async (data: AltInvestmentInput) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/alt-investments/`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<AltInvestment>;
    },
    update: async (id: number, data: Partial<AltInvestmentInput>) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/alt-investments/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(data),
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
      return res.json() as Promise<AltInvestment>;
    },
    delete: async (id: number) => {
      const headers = await authHeaders();
      const res = await fetch(`${BASE}/alt-investments/${id}`, {
        method: "DELETE",
        headers,
      });
      if (!res.ok) throw new Error(`Error: ${await res.text()}`);
    },
  },
};
