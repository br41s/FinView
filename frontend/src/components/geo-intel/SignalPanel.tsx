import { Fragment, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, ExternalLink, Target } from "lucide-react";
import { scopeLabel, thesisSegments, tradabilityHint, type GeoSignal } from "@/lib/geo";
import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { PrecioTab } from "@/components/instrument/PrecioTab";
import { FundamentalsCard } from "./FundamentalsCard";
import { ListSkeleton } from "./MapStates";

const DIR_COLORS = {
  bullish: "#6B7A3A",
  bearish: "#9B3D2C",
  neutral: "#9A6B1F",
} as const;

/**
 * Sends a ticker to the technical desk. Ideas surfaces the thesis; Zonas Clave
 * is where you check whether the chart agrees — so a recommended ticker needs a
 * one-click way over, not just a link that leaves you to add it by hand.
 *
 * Owns its own state instead of taking props: the panel re-renders on every
 * signal selection and poll, and threading add/busy/error for N tickers through
 * it would be prop drilling. `enable_zonas` on the backend is idempotent-ish
 * (409 when already followed), so a double click is harmless.
 */
type AddState = "idle" | "busy" | "added" | "error";

function AddToZonasButton({ symbol }: { symbol: string }) {
  // State is stored with the symbol it belongs to: a different symbol reads as
  // "checking" by derivation, with no synchronous reset inside the effect.
  const [membership, setMembership] = useState<{ symbol: string; state: AddState } | null>(null);
  const state = membership?.symbol === symbol ? membership.state : "checking";

  useEffect(() => {
    let cancelled = false;
    api.zonasClav
      .watchlist()
      .then((items) => {
        if (cancelled) return;
        const already = items.some((i) => i.ticker.toUpperCase() === symbol.toUpperCase());
        setMembership({ symbol, state: already ? "added" : "idle" });
      })
      // Can't tell whether it's already there — offer the button anyway. The
      // backend 409s on a duplicate, which is a better failure than hiding it.
      .catch((e) => {
        bestEffort("zonas-clave watchlist membership")(e);
        if (!cancelled) setMembership({ symbol, state: "idle" });
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const add = useCallback(async () => {
    setMembership({ symbol, state: "busy" });
    try {
      await api.zonasClav.addTicker(symbol);
      setMembership({ symbol, state: "added" });
    } catch {
      setMembership({ symbol, state: "error" });
    }
  }, [symbol]);

  if (state === "checking") return null;

  if (state === "added") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-[rgba(31,27,22,0.45)]">
        <Check className="h-3 w-3" />
        En Zonas Clave
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={add}
      disabled={state === "busy"}
      title="Añadir a Zonas Clave y lanzar el análisis de soportes/resistencias"
      className="inline-flex items-center gap-1 text-[11px] text-[rgba(31,27,22,0.6)] transition-colors hover:text-[#1F1B16] disabled:opacity-50"
    >
      <Target className="h-3 w-3" />
      {state === "busy" ? "Añadiendo…" : state === "error" ? "Error — reintentar" : "Añadir a Zonas Clave"}
    </button>
  );
}

// Friendly names for the ingest feed keys stored on GeoSignal.source. Keyed
// lowercase so mixed-case keys (usgs, EONET, GDACS) all resolve; unknown feeds
// fall back to the raw key upper-cased rather than rendering blank.
const SOURCE_LABELS: Record<string, string> = {
  usgs: "USGS",
  eonet: "NASA EONET",
  gdacs: "GDACS",
  firms: "NASA FIRMS",
  alerts: "Alertas meteo",
  opensky: "OpenSky",
  windy: "Windy",
  gdelt: "GDELT",
  ofac: "OFAC",
  fedreg: "Federal Register",
  ais: "AIS marítimo",
  compound: "Regla compuesta",
};

function sourceLabel(source?: string) {
  if (!source) return "Desconocida";
  return SOURCE_LABELS[source.toLowerCase()] ?? source.toUpperCase();
}

function formatRegistered(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("es-ES", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

type Props = {
  signals: GeoSignal[];
  selected: GeoSignal | null;
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  onSelect: (s: GeoSignal | null) => void;
  loading?: boolean;
};

export function SignalPanel({ signals, selected, hoveredId, onHover, onSelect, loading }: Props) {
  return (
    <aside className="flex max-h-[60vh] w-full shrink-0 flex-col border-t border-[rgba(31,27,22,0.14)] bg-[#FEFCF5] lg:h-full lg:max-h-none lg:w-[380px] lg:border-l lg:border-t-0">
      {selected ? (
        <DetailView signal={selected} onBack={() => onSelect(null)} />
      ) : (
        <ListView
          signals={signals}
          hoveredId={hoveredId}
          onHover={onHover}
          onSelect={onSelect}
          loading={loading}
        />
      )}
    </aside>
  );
}

function ListView({
  signals,
  hoveredId,
  onHover,
  onSelect,
  loading,
}: {
  signals: GeoSignal[];
  hoveredId: string | null;
  onHover: (id: string | null) => void;
  onSelect: (s: GeoSignal) => void;
  loading?: boolean;
}) {
  const sorted = [...signals].sort((a, b) => b.importance - a.importance);
  return (
    <>
      <div className="border-b border-[rgba(31,27,22,0.14)] px-5 py-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
          Signals
        </p>
        <h2
          className="mt-0.5 text-lg text-[#1F1B16]"
          style={{ fontFamily: "var(--fv-font-fraunces), serif", fontWeight: 500 }}
        >
          Live feed
        </h2>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <ListSkeleton />
        ) : sorted.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
            <p className="text-[12px] text-[rgba(31,27,22,0.6)]">
              No signals match the current filters.
            </p>
          </div>
        ) : (
          sorted.map((s) => {
          const color = DIR_COLORS[s.direction];
          const accent =
            s.direction === "bearish"
              ? "#9B3D2C"
              : s.direction === "bullish"
                ? "#6B7A3A"
                : "transparent";
          const isHover = hoveredId === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onMouseEnter={() => onHover(s.id)}
              onMouseLeave={() => onHover(null)}
              onClick={() => onSelect(s)}
              className="block w-full border-b border-[rgba(31,27,22,0.08)] px-5 py-3 text-left transition-colors"
              style={{
                borderLeft: `2px solid ${accent === "transparent" ? "transparent" : accent + "55"}`,
                backgroundColor: isHover ? "rgba(154,107,31,0.05)" : "transparent",
              }}
            >
              <div className="flex items-start gap-3">
                <span
                  className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: color }}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium leading-snug text-[#1F1B16]">
                    {s.headline}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-[rgba(31,27,22,0.6)]">
                    {s.location} · {relTime(s.timestamp)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span
                    className="text-[12px] tabular-nums text-[#1F1B16]"
                    style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
                  >
                    {s.importance}
                  </span>
                  <DirChip dir={s.direction} />
                </div>
              </div>
            </button>
          );
          })
        )}
      </div>
    </>
  );
}

function DirChip({ dir }: { dir: GeoSignal["direction"] }) {
  const color = DIR_COLORS[dir];
  const label = dir === "bullish" ? "BULL" : dir === "bearish" ? "BEAR" : "NEUT";
  return (
    <span
      className="rounded-sm px-1.5 py-[1px] text-[9px] tracking-wider"
      style={{
        fontFamily: "var(--fv-font-jetbrains), monospace",
        color,
        backgroundColor: color + "1A",
      }}
    >
      {label}
    </span>
  );
}

const OUTCOME_COLORS = {
  CORRECT: "#6B7A3A",
  INCORRECT: "#9B3D2C",
  NEUTRAL: "#9A6B1F",
} as const;

function checkpointLabel(horizon: string) {
  return `+${horizon}`;
}

function DetailView({ signal, onBack }: { signal: GeoSignal; onBack: () => void }) {
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-[rgba(31,27,22,0.14)] px-5 py-3">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 text-[11px] text-[rgba(31,27,22,0.6)] transition-colors hover:text-[#1F1B16]"
        >
          <ArrowLeft size={12} />
          Back to feed
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
        <h2
          className="text-[22px] leading-snug text-[#1F1B16]"
          style={{ fontFamily: "var(--fv-font-fraunces), serif", fontWeight: 500, letterSpacing: "-0.01em" }}
        >
          {signal.headline}
        </h2>
        <p className="mt-2 text-[12px] text-[rgba(31,27,22,0.6)]">
          <span className="capitalize">{signal.category}</span> · {signal.location}
        </p>

        <div className="mt-5 grid grid-cols-2 gap-px overflow-hidden rounded-md border border-[rgba(31,27,22,0.14)] bg-[rgba(31,27,22,0.08)]">
          <Stat label="Importance" value={String(signal.importance)} />
          <Stat label="Confidence" value={`${Math.round(signal.confidence * 100)}%`} />
          <Stat label="Risk" value={`${signal.riskScore.toFixed(1)} / 10`} />
          <Stat
            label="Direction"
            value={signal.direction.toUpperCase()}
            valueColor={DIR_COLORS[signal.direction]}
          />
        </div>

        <div className="mt-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
            Why this was triggered
          </p>

          <div className="mt-2 rounded-md border border-[rgba(31,27,22,0.12)] bg-[rgba(154,107,31,0.05)] px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-[rgba(31,27,22,0.7)]">
              <span>
                <span className="text-[rgba(31,27,22,0.5)]">Fuente:</span>{" "}
                <span className="font-medium text-[#1F1B16]">{sourceLabel(signal.source)}</span>
              </span>
              <span>
                <span className="text-[rgba(31,27,22,0.5)]">Registrada:</span>{" "}
                <span
                  className="tabular-nums text-[#1F1B16]"
                  style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
                >
                  {formatRegistered(signal.timestamp)}
                </span>
              </span>
            </div>
            {signal.sourceUrl ? (
              <a
                href={signal.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-[#9A6B1F] transition-opacity hover:opacity-70"
              >
                <ExternalLink className="h-3 w-3" />
                Ver fuente
              </a>
            ) : (
              <p className="mt-1.5 text-[10px] text-[rgba(31,27,22,0.4)]">
                Esta fuente no publica un enlace por evento.
              </p>
            )}
          </div>

          {signal.generated ? (
            <div className="mt-2.5 flex flex-col gap-1.5 text-[12px]">
              <span
                className="w-fit rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide"
                style={{ color: "#825416", borderColor: "rgba(130,84,22,0.35)", backgroundColor: "rgba(130,84,22,0.08)" }}
                title="Ningún criterio escrito cubre este evento: la tesis la propuso el modelo y no alimenta el aprendizaje de reglas."
              >
                Tesis generada por IA · sin regla
              </span>
              {signal.thesis && (
                <p className="flex flex-wrap gap-x-2 text-[rgba(31,27,22,0.85)]">
                  {thesisSegments(signal.thesis).map((seg, i) => (
                    <span key={i} className="inline-flex items-center gap-x-2">
                      {i > 0 && <span className="text-[rgba(31,27,22,0.35)]">→</span>}
                      {seg}
                    </span>
                  ))}
                </p>
              )}
              {signal.narrative && (
                <p className="text-[rgba(31,27,22,0.7)]">{signal.narrative}</p>
              )}
            </div>
          ) : signal.rules.length === 0 ? (
            <p className="mt-2.5 text-[12px] text-[rgba(31,27,22,0.5)]">
              No specific rule matched — scored on base event severity.
            </p>
          ) : (
            <div className="mt-2.5 flex flex-col gap-2.5">
              {signal.rules.map((r) => {
                const scope = scopeLabel(r.scope);
                const chain = thesisSegments(r.thesis);
                return (
                  <div key={r.id} className="rounded-md border border-[rgba(31,27,22,0.12)] bg-[#FEFCF5] px-3 py-2.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[12px] font-medium leading-snug text-[#1F1B16]">
                        {scope && (
                          <span
                            className="mr-1.5 rounded-sm bg-[rgba(31,27,22,0.06)] px-1 py-[1px] align-[1px] text-[9px] font-normal uppercase tracking-wider text-[rgba(31,27,22,0.55)]"
                            title="Alcance del evento que disparó la regla"
                          >
                            {scope}
                          </span>
                        )}
                        {r.description}
                      </p>
                      <span
                        className="shrink-0 text-[10px] tabular-nums text-[rgba(31,27,22,0.5)]"
                        style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
                        title="Confianza de la regla (base + ajuste del auditor)"
                      >
                        {Math.round(r.confidence * 100)}%
                      </span>
                    </div>
                    {/* A written thesis is a chain: physical effect → price/flow →
                        instrument. Run together it reads as one sentence and the
                        three links stop being separable; spaced out you can see
                        which link you disagree with. */}
                    <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11px] leading-snug text-[rgba(31,27,22,0.6)]">
                      {chain.map((segment, i) => (
                        <Fragment key={i}>
                          {i > 0 && (
                            <span aria-hidden className="text-[rgba(31,27,22,0.35)]">
                              →
                            </span>
                          )}
                          <span>{segment}</span>
                        </Fragment>
                      ))}
                    </div>
                    {(r.category || r.trigger) && (
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        {r.category && (
                          <span className="rounded-sm bg-[rgba(31,27,22,0.06)] px-1.5 py-[1px] text-[9px] uppercase tracking-wider text-[rgba(31,27,22,0.55)]">
                            {r.category}
                          </span>
                        )}
                        {r.trigger && (
                          <span
                            className="rounded-sm bg-[rgba(31,27,22,0.06)] px-1.5 py-[1px] text-[10px] text-[rgba(31,27,22,0.6)]"
                            style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
                            title="Condición que disparó esta regla"
                          >
                            {r.trigger}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="mt-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
            Affected tickers
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {signal.tickers.length === 0 ? (
              <span className="text-[12px] text-[rgba(31,27,22,0.5)]">None tagged</span>
            ) : (
              signal.tickers.map((t) => {
                const color = DIR_COLORS[t.direction];
                const arrow = t.direction === "bullish" ? "↑" : t.direction === "bearish" ? "↓" : "•";
                const isExpanded = expandedSymbol === t.symbol;
                const hint = tradabilityHint(t);
                const base =
                  t.priceAtSignal != null
                    ? `Precio al disparo: ${t.priceAtSignal.toFixed(2)} · Ver instrumento`
                    : "Ver instrumento";
                return (
                  <button
                    key={t.symbol}
                    type="button"
                    title={hint.tooltip ? `${base} · ${hint.tooltip}` : base}
                    onClick={() => setExpandedSymbol(isExpanded ? null : t.symbol)}
                    className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] transition-opacity hover:opacity-70"
                    style={{
                      fontFamily: "var(--fv-font-jetbrains), monospace",
                      color,
                      backgroundColor: color + "1A",
                      // A chip with no retail route in the EU still belongs in the
                      // thesis — it just must not read as buyable. Dimmed + dashed,
                      // never hidden. `options_only` stays at full weight: the owner
                      // trades IBKR options, so it is a route, not a dead end.
                      border: hint.muted ? `1px dashed ${color}80` : "1px solid transparent",
                      opacity: hint.muted ? 0.55 : 1,
                    }}
                  >
                    <span>
                      {arrow} {t.symbol}
                    </span>
                    {hint.badge && (
                      <span
                        className="rounded-sm px-1 py-[1px] text-[8px] uppercase tracking-wider"
                        style={{ backgroundColor: color + "26" }}
                      >
                        {hint.badge}
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>
          {expandedSymbol && (
            <div className="mt-3 rounded-md border border-[rgba(31,27,22,0.14)] bg-[#FEFCF5] p-3">
              {(() => {
                // The chip's tooltip names the alternative; the expansion is where
                // you act on it, so it gets a line you can read without hovering.
                const alt = signal.tickers.find((t) => t.symbol === expandedSymbol)?.alternate;
                return alt?.trim() ? (
                  <p className="mb-2 text-[11px] leading-snug text-[rgba(31,27,22,0.6)]">
                    <span className="text-[rgba(31,27,22,0.45)]">Alternativa UCITS/UE:</span>{" "}
                    <span className="text-[#1F1B16]">{alt.trim()}</span>
                  </p>
                ) : null;
              })()}
              <PrecioTab symbol={expandedSymbol} />
              <FundamentalsCard symbol={expandedSymbol} />
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[rgba(31,27,22,0.12)] pt-3 text-[11px]">
                <AddToZonasButton symbol={expandedSymbol} />
                <Link
                  href={`/zonas-clave?ticker=${encodeURIComponent(expandedSymbol)}`}
                  className="text-[rgba(31,27,22,0.6)] transition-colors hover:text-[#1F1B16]"
                >
                  Ver en Zonas Clave →
                </Link>
                <Link
                  href={`/options?ticker=${encodeURIComponent(expandedSymbol)}`}
                  className="text-[rgba(31,27,22,0.6)] transition-colors hover:text-[#1F1B16]"
                >
                  Ver en Opciones →
                </Link>
              </div>
            </div>
          )}
        </div>

        <div className="mt-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
            Checkpoints
          </p>
          <div className="mt-4 relative">
            <div className="absolute left-0 right-0 top-[7px] h-px bg-[rgba(31,27,22,0.14)]" />
            <div className="relative flex justify-between">
              {signal.checkpoints.map((c) => {
                // An evaluated row with no verdict is pending too. `c.outcome ??
                // "NEUTRAL"` used to paint it amber, which read as a measured
                // "no move" the auditor never made.
                const pending = c.evaluatedAt == null || c.outcome == null;
                const dotColor = pending ? undefined : OUTCOME_COLORS[c.outcome!];
                // Amber filled vs red filled at 3.5 px is not a distinction a
                // human makes, and NEUTRAL is the opposite of INCORRECT: it
                // means nothing measurable happened. Hollow says "no reading".
                const hollow = pending || c.outcome === "NEUTRAL";
                // NEUTRAL with a score is a tie (1-for-2), not "nothing moved".
                const title = pending
                  ? "pendiente"
                  : c.outcome === "NEUTRAL"
                  ? `${c.score == null ? "sin movimiento medible" : "sin veredicto (empate)"}${c.detail ? ` — ${c.detail}` : ""}`
                  : `${c.score != null ? Math.round(c.score) + "% correct" : "sin movimiento medible"}${c.detail ? ` — ${c.detail}` : ""}`;
                return (
                  <div key={c.horizon} className="flex flex-col items-center gap-2" title={title}>
                    <span
                      className="h-3.5 w-3.5 rounded-full border-2"
                      style={{
                        borderColor: pending ? "rgba(31,27,22,0.25)" : dotColor,
                        backgroundColor: hollow ? "#FEFCF5" : dotColor,
                      }}
                    />
                    <span
                      className="text-[10px] text-[rgba(31,27,22,0.6)]"
                      style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
                    >
                      {checkpointLabel(c.horizon)}
                    </span>
                  </div>
                );
              })}
            </div>
            {(() => {
              const lastEvaluated = [...signal.checkpoints]
                .reverse()
                .find((c) => c.evaluatedAt != null && c.outcome != null);
              return (
                <p className="mt-3 text-[11px] text-[rgba(31,27,22,0.5)]">
                  {lastEvaluated
                    ? `${checkpointLabel(lastEvaluated.horizon)}: ${lastEvaluated.outcome === "NEUTRAL" || lastEvaluated.score == null ? "sin movimiento medible" : Math.round(lastEvaluated.score) + "% correct"}${lastEvaluated.detail ? ` — ${lastEvaluated.detail}` : ""}`
                    : "Outcome tracking pending — checkpoints fill in as the signal ages."}
                </p>
              );
            })()}
          </div>
        </div>
      </div>
      <div className="border-t border-[rgba(31,27,22,0.14)] px-5 py-3">
        <p
          className="text-[10px] text-[rgba(31,27,22,0.5)]"
          style={{ fontFamily: "var(--fv-font-jetbrains), monospace" }}
        >
          {new Date(signal.timestamp).toUTCString()} · {signal.status.toUpperCase()}
        </p>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  valueColor = "#1F1B16",
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <div className="bg-[#FEFCF5] px-3 py-3">
      <p className="text-[9px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
        {label}
      </p>
      <p
        className="mt-1 text-[18px] tabular-nums"
        style={{ fontFamily: "var(--fv-font-jetbrains), monospace", color: valueColor }}
      >
        {value}
      </p>
    </div>
  );
}