import { getSession, signOut } from "next-auth/react";
import { bestEffort } from "./bestEffort";

import type { GeoAccuracy, GeoSignal } from "@/lib/geo";
import type {
  CapitalGain,
  CapitalGainsBreakdown,
  Casilla,
  CompanyDividendsYearly,
  CrossBrokerLot,
  DashboardStats,
  DataIssue,
  DividendSummary,
  DividendYield,
  DividendsByCountry,
  DividendsMonthly,
  FIFOAdjustment,
  FiscalProfile,
  ImportRecord,
  ImportResult,
  ManualSavingsIncome,
  OptionAssignment,
  PatrimonioComposition,
  SavingsEstimate,
  TopDividendPayer,
  WithholdingsByCountry,
  YearlyComparisonResult,
} from "@/lib/types";
import { apiError } from "@/lib/apiError";
import type { GeoCycleRun } from "@/lib/geoHealth";

const BASE = "/api";

export interface GeoSchedulerStatus {
  running: boolean;
  external_scheduler: boolean;
  interval_minutes: number;
  total_signals: number;
  active_signals: number;
  last_signal_at: string | null;
  // The pipeline's own heartbeat. `last_signal_at` cannot distinguish a stopped
  // cycle from a quiet one; this can. See lib/geoHealth.ts.
  last_run: GeoCycleRun | null;
  // FRED macro snapshot; the regime adds one risk point to geopolitical events.
  macro?: GeoMacro | null;
}

export interface GeoMacro {
  regime: "risk_off" | "neutral" | "risk_on" | string;
  vix: number | null;
  yield_spread: number | null;
  financial_stress: number | null;
  hy_spread: number | null;
  as_of: string | null;
}

export interface GeoRunResult {
  status: string;
  events?: number | null;
  new_signals?: number | null;
  notified?: number | null;
}

/** The last options-agent cycle report (GET /options/agent/last-analysis). */
export interface LastAnalysis {
  timestamp: string | null;
  cycle: number | null;
  tickers_analyzed: number | null;
  alerts: number | null;
  unusual: number | null;
  market_sentiment: string | null;
  claude_analysis: string | null;
  ai_configured: boolean;
  macro: GeoMacro | null;
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

export interface ZcTickerSearchResult {
  ticker: string;
  name: string;
  exchange: string;
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

/**
 * Fundamental snapshot from yfinance `.info`. Every field is optional: `.info`
 * is scraped, has no stable contract, and returns a mostly-empty dict for plenty
 * of valid tickers. An empty object means "nothing to show", not "bad ticker" —
 * render nothing rather than zeros.
 */
export interface Fundamentals {
  name?: string;
  sector?: string;
  industry?: string;
  currency?: string;
  market_cap?: number;
  trailing_pe?: number;
  forward_pe?: number;
  price_to_book?: number;
  dividend_yield?: number;
  profit_margins?: number;
  debt_to_equity?: number;
  return_on_equity?: number;
  revenue_growth?: number;
  beta?: number;
}

export interface TechnicalSignal {
  id: number;
  created_at: string;
  ticker: string;
  zone_level: number;
  zone_type: string;
  zone_strength: number | null;
  zone_touches: number | null;
  price_at_signal: number;
  distance_pct: number;
  // Which side price is approaching the level from. Derived from price vs level,
  // not from zone_type, which goes stale once a level flips.
  approach: "from_below" | "from_above";
  direction: "BULLISH" | "BEARISH";
  // null = the LLM couldn't score it (no key, failure, bad answer). NOT a low
  // probability — render as "sin puntuar", never as 0.
  break_probability: number | null;
  rationale: string | null;
  // true when break_probability cleared the (uncalibrated) alert threshold.
  alerted: boolean;
}

export interface OhlcBar {
  date: string;
  // Epoch seconds — present only for intraday bars (interval !== "1d"),
  // since lightweight-charts needs a precise timestamp rather than a
  // whole-day key once more than one bar falls on the same calendar day.
  time?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ZcSchedulerStatus {
  running: boolean;
  external_scheduler: boolean;
  last_run: string | null;
  total_items: number;
}

export interface ZcCalibrationBucket {
  n: number;
  measured: number; // correct + incorrect at 7d
  correct: number;
  accuracy_pct: number | null;
}

/** How the break-probability alert gate is doing against outcomes (GET /zonas-clave/calibration). */
export interface ZcCalibration {
  window_days: number;
  since: string;
  default_threshold: number;
  scored: number;
  evaluated: number;
  by_bucket: Record<string, ZcCalibrationBucket>;
  cumulative_from: Record<string, ZcCalibrationBucket>;
  suggested_threshold: number | null;
  effective_threshold: number;
  calibrated: boolean;
}

// ── 5-minute client-side cache for read-heavy GET endpoints ──────────
// Backed by sessionStorage (not a module-level Map) so it survives client-side
// route navigation regardless of how the bundler chunks lib/api.ts, and even a
// same-tab hard refresh — an in-memory Map only survives as long as the module
// instance does, which is not guaranteed across navigations.
const _CACHE_PREFIX = "fv_cache:";
const _CACHE_TTL = 5 * 60 * 1000; // 5 min in ms

function _getCached(key: string): unknown | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(_CACHE_PREFIX + key);
    if (!raw) return null;
    const entry = JSON.parse(raw) as { data: unknown; ts: number };
    if (Date.now() - entry.ts > _CACHE_TTL) {
      window.sessionStorage.removeItem(_CACHE_PREFIX + key);
      return null;
    }
    return entry.data;
  } catch {
    return null;
  }
}
function _setCached(key: string, data: unknown): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      _CACHE_PREFIX + key,
      JSON.stringify({ data, ts: Date.now() }),
    );
  } catch {
    // Quota exceeded or storage unavailable (e.g. private mode) — degrade to
    // no caching for this entry rather than breaking the request.
  }
}
export function invalidateCache(prefix?: string): void {
  if (typeof window === "undefined") return;
  try {
    const toRemove: string[] = [];
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const key = window.sessionStorage.key(i);
      if (!key || !key.startsWith(_CACHE_PREFIX)) continue;
      const path = key.slice(_CACHE_PREFIX.length);
      if (!prefix || path.startsWith(prefix)) toRemove.push(key);
    }
    for (const key of toRemove) window.sessionStorage.removeItem(key);
  } catch {
    // ignore — nothing to invalidate if storage is unavailable
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

// The backend token lives 90 days from login and is never refreshed, while the
// NextAuth cookie rolls forward on activity, so a session can outlive its
// token. Once a freshly resolved token is still refused, every section of the
// app reads "no se pudieron cargar los datos" until the user guesses to sign
// out (2026-10-14). End the session and land on /login instead. One-shot: the
// dashboard fires ~16 requests at once and they all come back 401 together.
let _endingSession = false;

function endDeadSession(): void {
  if (_endingSession || typeof window === "undefined") return;
  _endingSession = true;
  clearAuthToken();
  void signOut({ callbackUrl: "/login" });
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

/**
 * One authenticated round-trip: bearer header, a single retry on a stale 401,
 * and `apiError` on any non-OK status. JSON reads, JSON mutations, multipart
 * uploads and CSV downloads all sit on top, so no call path can skip the retry
 * or forget the `ok` check again.
 */
async function request(path: string, init?: RequestInit, _retried = false): Promise<Response> {
  const headers = await authHeaders();
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  });
  // A 401 means the cached token is stale (rotated/expired/logged out elsewhere).
  // Drop it and retry once with a freshly-resolved token; if that one is refused
  // too, the session itself is dead.
  if (res.status === 401) {
    if (!_retried) {
      clearAuthToken();
      return request(path, init, true);
    }
    endDeadSession();
  }
  if (!res.ok) throw await apiError(res);
  return res;
}

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await request(path, init);
  // 204 carries no body; res.json() would throw on the empty payload.
  return res.status === 204 ? (undefined as T) : res.json();
}

/** JSON mutation. `body` is serialised when given; omit it for bodiless calls. */
async function send<T = unknown>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  return fetchJSON<T>(
    path,
    body === undefined
      ? { method }
      : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
}

/** Save a server-generated file through the browser, via the same retry path. */
async function download(path: string, filename: string): Promise<void> {
  const res = await request(path);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * POST a multipart body through fetchJSON, so uploads inherit its stale-token
 * retry. The six broker uploads each rebuilt this by hand and therefore skipped
 * that retry: a cached token that expired mid-session turned a recoverable
 * request into a failed import.
 *
 * Content-Type is deliberately unset — the browser adds it with the multipart
 * boundary, and naming it here would corrupt the body.
 */
async function postForm<T>(path: string, files: File | File[], field = "file"): Promise<T> {
  const form = new FormData();
  for (const file of Array.isArray(files) ? files : [files]) {
    form.append(field, file);
  }
  const data = await fetchJSON<T>(path, { method: "POST", body: form });
  invalidateCache();
  return data;
}

async function fetchCached<T>(path: string): Promise<T> {
  const hit = _getCached(path);
  if (hit !== null) return hit as T;
  const data = await fetchJSON<T>(path);
  _setCached(path, data);
  return data;
}

// Every broker import returns the same envelope; the uploads used to be six
// byte-identical functions returning implicit `any`.
export const uploadTRReport = (file: File) => postForm<ImportResult>("/imports/tr", file);
export const uploadDGReport = (file: File) => postForm<ImportResult>("/imports/degiro", file);
export const uploadIBKRReport = (file: File) => postForm<ImportResult>("/imports/ibkr", file);
export const uploadINGReport = (file: File) => postForm<ImportResult>("/imports/ing", file);
export const uploadEToroReport = (file: File) => postForm<ImportResult>("/imports/etoro", file);
// BBVA takes 1-3 PDFs in one submission, under a plural field name.
export const uploadBBVAReport = (files: File[]) =>
  postForm<ImportResult>("/imports/bbva", files, "files");

export async function deleteImport(importId: number) {
  const data = await send("DELETE", `/imports/${importId}`);
  invalidateCache();
  return data;
}

export async function deleteAllImports() {
  const data = await send("DELETE", "/imports/all");
  invalidateCache();
  return data;
}

export async function resolveIssue(
  issueId: number,
  action: string,
  data?: Record<string, unknown>,
) {
  const result = await send<DataIssue>("POST", `/imports/issues/${issueId}/resolve`, {
    action,
    data,
  });
  invalidateCache();
  return result;
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
    fetchCached<DashboardStats>(`/fiscal/dashboard${qs({ fiscal_year: year })}`),
  casillas: (year?: number) =>
    fetchCached<Casilla[]>(`/fiscal/casillas${qs({ fiscal_year: year })}`),
  exportFiscal: async (year: number, format: "json" | "csv" = "json") => {
    if (format === "csv") {
      await download(`/fiscal/export/${year}?format=csv`, `finview_casillas_${year}.csv`);
      return null;
    }
    return fetchJSON(`/fiscal/export/${year}?format=json`);
  },
  dividends: (year?: number) =>
    fetchCached<DividendSummary[]>(`/transactions/dividends/summary${qs({ fiscal_year: year })}`),
  capitalGains: (year?: number) =>
    fetchCached<CapitalGain[]>(`/transactions/capital-gains${qs({ fiscal_year: year })}`),
  crossBrokerLots: (year: number) =>
    fetchCached<CrossBrokerLot[]>(`/fiscal/cross-broker-lots${qs({ fiscal_year: year })}`),
  fifoAdjustments: (year: number) =>
    fetchCached<FIFOAdjustment[]>(`/fiscal/fifo-adjustments${qs({ fiscal_year: year })}`),
  optionAssignments: (year: number) =>
    fetchCached<OptionAssignment[]>(`/fiscal/option-assignments${qs({ fiscal_year: year })}`),
  yearlyComparison: () => fetchCached<YearlyComparisonResult>("/fiscal/yearly-comparison"),

  // Fiscal onboarding — savings-base estimate (v1 individual)
  fiscalProfile: (year: number) => fetchJSON<FiscalProfile>(`/fiscal/profile/${year}`),
  saveFiscalProfile: async (
    year: number,
    body: {
      age: number | null;
      disability: "general" | "severe" | null;
      health_data_consent: boolean;
      descendants: number;
      general_base: string;
      prior_rcm_loss: string;
      prior_gp_loss: string;
    },
  ) => {
    const data = await send("PUT", `/fiscal/profile/${year}`, body);
    invalidateCache(`/fiscal/estimate/${year}`);
    return data;
  },
  manualIncome: (year: number) =>
    fetchJSON<ManualSavingsIncome[]>(`/fiscal/manual-income/${year}`),
  addManualIncome: async (body: {
    fiscal_year: number;
    category: "INTEREST" | "DIVIDEND" | "GAIN" | "LOSS";
    label: string;
    amount_eur: string;
    withholding_eur: string;
  }) => {
    const data = await send("POST", "/fiscal/manual-income", body);
    invalidateCache(`/fiscal/estimate/${body.fiscal_year}`);
    return data;
  },
  deleteManualIncome: async (id: number, year: number) => {
    // `send` throws on a non-OK status: without that the request could 404 or
    // 500 and the UI would still report the entry as deleted, then show it
    // again on the next load.
    await send("DELETE", `/fiscal/manual-income/${id}`);
    invalidateCache(`/fiscal/estimate/${year}`);
  },
  savingsEstimate: (year: number) => fetchCached<SavingsEstimate>(`/fiscal/estimate/${year}`),
  exportSavingsEstimate: (year: number) =>
    download(`/fiscal/estimate/${year}/export?format=csv`, `finview_estimacion_ahorro_${year}.csv`),
  transactions: (params?: Record<string, string>) => {
    const qstr = params ? "?" + new URLSearchParams(params).toString() : "";
    return fetchJSON(`/transactions/${qstr}`);
  },
  imports: () => fetchJSON<ImportRecord[]>("/imports/"),

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
    // Fire-and-forget cache warm: the caller does not await it and the pages
    // work without it, so a failure only costs a slower first price load.
    warmPrices: () =>
      send("POST", "/portfolio/warm-prices").catch(bestEffort("portfolio price cache warm")),
  },

  // Accounts
  accounts: {
    list: () => fetchJSON("/accounts/"),
    create: (data: { broker: string; account_id: string; name?: string; currency?: string }) =>
      send("POST", "/accounts/", data),
    update: (id: number, data: { name?: string; currency?: string }) =>
      send("PATCH", `/accounts/${id}`, data),
    delete: async (id: number) => {
      await send("DELETE", `/accounts/${id}`);
    },
  },

  // Billing
  billing: {
    subscription: () => fetchJSON("/billing/subscription"),
    checkout: (priceId: string) =>
      send<{ url: string }>("POST", "/billing/checkout", { price_id: priceId }),
    portal: () => send<{ url: string }>("POST", "/billing/portal"),
  },

  // Account creation. Unauthenticated, but it still goes through request() so a
  // rejected sign-up surfaces the backend's Spanish `detail` like every other call.
  auth: {
    register: (body: { email: string; name: string; password: string; accept_terms: boolean }) =>
      send("POST", "/auth/register", body),
  },

  // The signed-in user's own account: consent, data export, deletion.
  me: {
    get: () => fetchJSON<{ terms_accepted: boolean }>("/auth/me"),
    acceptTerms: () => send("POST", "/users/me/accept-terms"),
    exportData: () => download("/users/me/export", "finview_mis_datos.json"),
    deleteAccount: (password: string) => send("POST", "/users/me/delete", { password }),
  },

  // Charts — cached client-side (5 min); invalidated on import/delete.
  charts: {
    dividendsByCountry: (year?: number) =>
      fetchCached<DividendsByCountry[]>(`/charts/dividends-by-country${qs({ fiscal_year: year })}`),
    dividendsMonthly: (year?: number) =>
      fetchCached<DividendsMonthly[]>(`/charts/dividends-monthly${qs({ fiscal_year: year })}`),
    topDividendPayers: (year?: number, limit = 10) =>
      fetchCached<TopDividendPayer[]>(
        `/charts/top-dividend-payers${qs({ limit, fiscal_year: year })}`,
      ),
    capitalGainsBreakdown: (year?: number) =>
      fetchCached<CapitalGainsBreakdown[]>(
        `/charts/capital-gains-breakdown${qs({ fiscal_year: year })}`,
      ),
    patrimonioComposition: (year?: number) =>
      fetchCached<PatrimonioComposition[]>(
        `/charts/patrimonio-composition${qs({ fiscal_year: year })}`,
      ),
    dividendYield: (year?: number) =>
      fetchCached<DividendYield[]>(`/charts/dividend-yield${qs({ fiscal_year: year })}`),
    withholdingsByCountry: (year?: number) =>
      fetchCached<WithholdingsByCountry[]>(
        `/charts/withholdings-by-country${qs({ fiscal_year: year })}`,
      ),
    dividendsByCompanyYearly: () =>
      fetchCached<CompanyDividendsYearly[]>("/charts/dividends-by-company-yearly"),
    priceHistory: (ticker: string, period = "2y", interval = "1d") =>
      fetchJSON<OhlcBar[]>(`/charts/price-history${qs({ ticker, period, interval })}`),
    fundamentals: (ticker: string) =>
      fetchJSON<Fundamentals>(`/charts/fundamentals${qs({ ticker })}`),
  },

  // Options monitor
  options: {
    watchlist: () => fetchCached("/options/watchlist"),
    addToWatchlist: async (ticker: string, name = "") => {
      const data = await send("POST", "/options/watchlist", { ticker, name });
      invalidateCache("/options/watchlist");
      return data;
    },
    toggleWatchlistItem: async (id: number) => {
      const data = await send("PATCH", `/options/watchlist/${id}`);
      invalidateCache("/options/watchlist");
      return data;
    },
    removeFromWatchlist: async (id: number) => {
      await send("DELETE", `/options/watchlist/${id}`);
      invalidateCache("/options/watchlist");
    },
    snapshots: (ticker?: string, days = 7) =>
      fetchCached(`/options/snapshots${qs({ ticker, days })}`),
    tickerChain: (ticker: string, expiration?: string) =>
      fetchJSON(`/options/chain/${encodeURIComponent(ticker)}${expiration ? `?expiration=${encodeURIComponent(expiration)}` : ""}`),
    tickerExpirations: (ticker: string) =>
      fetchJSON(`/options/expirations/${encodeURIComponent(ticker)}`),
    hiddenPortfolioTickers: () =>
      fetchCached<string[]>("/options/portfolio/hidden"),
    hidePortfolioTicker: async (ticker: string) => {
      await send("POST", "/options/portfolio/hidden", { ticker });
      invalidateCache("/options/portfolio/hidden");
    },
    unhidePortfolioTicker: async (ticker: string) => {
      await send("DELETE", `/options/portfolio/hidden/${encodeURIComponent(ticker)}`);
      invalidateCache("/options/portfolio/hidden");
    },
    checkAvailability: (tickers: string[]) =>
      send<{ has_options: string[]; no_options: string[] }>(
        "POST",
        "/options/check-availability",
        { tickers },
      ),
    alerts: (ticker?: string, unread?: boolean, days = 7) =>
      fetchJSON(
        `/options/alerts${qs({
          ticker,
          unread: unread ? "true" : undefined,
          days,
        })}`,
      ),
    ackAlert: (id: number) => send("PATCH", `/options/alerts/${id}/ack`),
    ackAllAlerts: () => send("POST", "/options/alerts/ack-all"),
    unusual: (ticker?: string, days = 7) =>
      fetchJSON(`/options/unusual${qs({ ticker, days })}`),
    agentStatus: () => fetchJSON("/options/agent/status"),
    lastAnalysis: () => fetchJSON<LastAnalysis>("/options/agent/last-analysis"),
    runCycle: () => send<{ status: string }>("POST", "/options/agent/run"),
    analyzeTicker: (ticker: string) =>
      send<TickerAnalysis>("POST", "/options/agent/analyze-ticker", { ticker }),
    startAgent: () => send("POST", "/options/agent/start"),
    stopAgent: () => send("POST", "/options/agent/stop"),
    backtestSignals: (params?: { ticker?: string; days?: number }) =>
      fetchJSON(`/options/backtest${qs(params ?? {})}`),
    backtestStats: (ticker?: string) =>
      fetchJSON(`/options/backtest/stats${ticker ? qs({ ticker }) : ""}`),
    backtestCalibration: (days = 30) =>
      fetchJSON<{
        window_days: number;
        since: string;
        total: number;
        evaluated_7d: number;
        newest: string | null;
        by_type_alignment: Record<
          string,
          Record<string, { correct: number; total: number; accuracy_pct: number | null }>
        >;
        dedup_health: Record<
          string,
          { rows: number; ticker_days: number; rows_per_ticker_day: number | null }
        >;
      }>(`/options/backtest/calibration${qs({ days })}`),
    backtestEvaluate: () => send("POST", "/options/backtest/evaluate"),
    ask: (question: string, history: { role: string; content: string }[] = []) =>
      send<{ answer: string }>("POST", "/options/ask", { question, history }),
  },

  // Zonas Clave
  zonasClav: {
    watchlist: () => fetchJSON<ZcWatchlistItem[]>("/zonas-clave/watchlist"),

    search: (q: string) =>
      fetchJSON<ZcTickerSearchResult[]>(`/zonas-clave/search?q=${encodeURIComponent(q)}`),

    addTicker: (ticker: string, name = "") =>
      send<ZcWatchlistItem>("POST", "/zonas-clave/watchlist", { ticker, name }),

    removeTicker: async (id: number) => {
      await send("DELETE", `/zonas-clave/watchlist/${id}`);
    },

    analysis: (ticker: string) =>
      fetchJSON<ZcAnalysis>(`/zonas-clave/analysis/${encodeURIComponent(ticker)}`),

    allAnalyses: () => fetchJSON<ZcAnalysis[]>("/zonas-clave/analysis"),

    signals: (days = 7) =>
      fetchJSON<TechnicalSignal[]>(`/zonas-clave/signals${qs({ days })}`),

    triggerAnalysis: (ticker: string) =>
      send<ZcAnalysis>("POST", `/zonas-clave/analyze/${encodeURIComponent(ticker)}`),

    triggerAll: () => send<{ status: string }>("POST", "/zonas-clave/analyze-all"),

    schedulerStatus: () =>
      fetchJSON<ZcSchedulerStatus>("/zonas-clave/scheduler/status"),
    calibration: () => fetchJSON<ZcCalibration>("/zonas-clave/calibration"),

    startScheduler: () => send("POST", "/zonas-clave/scheduler/start"),

    stopScheduler: () => send("POST", "/zonas-clave/scheduler/stop"),
  },

  // Geo-Intel
  geo: {
    signals: (status: "active" | "resolved" | "all" = "active") =>
      fetchJSON<GeoSignal[]>(`/geo/signals?status=${status}`),
    run: () => send<GeoRunResult>("POST", "/geo/run"),
    schedulerStatus: () =>
      fetchJSON<GeoSchedulerStatus>("/geo/scheduler/status"),
    // Per-horizon hit rate + the learned rule table. `since` is an ISO date;
    // the backend defaults to 30 days ago, which keeps the pre-2026-09-06
    // checkpoints (scored by a close-against-itself comparison) out of the read.
    accuracy: (since?: string) =>
      fetchJSON<GeoAccuracy>(`/geo/accuracy${since ? `?since=${since}` : ""}`),
    // Zeroes every learned adjustment. The table is global, not per user, and
    // there is deliberately no UI for this — it is an owner's tool.
    resetRuleStats: () => send<{ reset: number }>("POST", "/geo/rule-stats/reset"),
    startScheduler: () => send("POST", "/geo/scheduler/start"),
    stopScheduler: () => send("POST", "/geo/scheduler/stop"),
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
    create: (data: AltInvestmentInput) => send<AltInvestment>("POST", "/alt-investments/", data),
    update: (id: number, data: Partial<AltInvestmentInput>) =>
      send<AltInvestment>("PATCH", `/alt-investments/${id}`, data),
    delete: async (id: number) => {
      await send("DELETE", `/alt-investments/${id}`);
    },
  },
};
