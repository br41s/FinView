/**
 * What each holding's own annual report says about AI (`GET /portfolio/ai-exposure`).
 *
 * Not a score: the backend counts mentions of AI in the 10-K's Risk Factors (SEC)
 * or in the whole ESEF report (EU), and keeps up to three quotes a model picks only
 * if every one is in the filing word for word. Shares are of portfolio value.
 */

export interface AiQuote {
  text: string;
  theme: string;
  theme_label: string;
}

export type AiQuotesStatus = "ok" | "none" | "unverified";

export interface AiHolding {
  isin: string;
  name: string;
  ticker: string | null;
  value_eur: number | null;
  status: "pending" | "ok" | "no_issuer" | "no_filing" | "no_section" | "too_large";
  detail: string;
  fiscal_year: number | null;
  source: "sec" | "esef" | null;
  scope: "risk_factors" | "annual_report" | null;
  scope_label: string | null;
  url: string | null;
  mentions: number | null;
  per_10k_words: number | null;
  quotes: AiQuote[];
  quotes_status: AiQuotesStatus | null;
  summary: string | null;
}

export interface AiTheme {
  key: string;
  label: string;
  pct: number;
}

export interface AiExposure {
  total_value_eur: number;
  read_pct: number;
  mentioning_pct: number;
  themes: AiTheme[];
  holdings: AiHolding[];
  pending: number;
}

function decimal(n: number): string {
  return n.toLocaleString("es-ES", { maximumFractionDigits: 1 });
}

/** "12 menciones · 3,1 por 10.000 palabras", or null before the report is read. */
export function mentionsText(h: Pick<AiHolding, "mentions" | "per_10k_words">): string | null {
  if (h.mentions === null) return null;
  const count = h.mentions === 1 ? "1 mención" : `${decimal(h.mentions)} menciones`;
  if (!h.mentions || h.per_10k_words === null) return count;
  return `${count} · ${decimal(h.per_10k_words)} por 10.000 palabras`;
}

/** Why a read report shows no quotes, or null when it shows some. */
export function quotesNote(h: Pick<AiHolding, "mentions" | "quotes_status">): string | null {
  if (h.quotes_status === "unverified") {
    return "Las citas propuestas por el modelo no coincidían palabra por palabra con el informe, así que no se muestran. Se reintentará en la próxima revisión.";
  }
  if (h.quotes_status === "none") {
    return h.mentions
      ? "Las menciones no describen qué supone la IA para el negocio."
      : "El texto leído no menciona la IA.";
  }
  return null;
}
