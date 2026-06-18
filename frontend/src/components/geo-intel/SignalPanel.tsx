import { ArrowLeft } from "lucide-react";
import type { GeoSignal } from "@/lib/geo";
import { ListSkeleton } from "./MapStates";

const DIR_COLORS = {
  bullish: "#6B7A3A",
  bearish: "#9B3D2C",
  neutral: "#9A6B1F",
} as const;

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
    <aside className="hidden h-full w-[380px] shrink-0 flex-col border-l border-[rgba(31,27,22,0.14)] bg-[#FEFCF5] lg:flex">
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
          style={{ fontFamily: "Fraunces, serif", fontWeight: 500 }}
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
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
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
        fontFamily: "JetBrains Mono, monospace",
        color,
        backgroundColor: color + "1A",
      }}
    >
      {label}
    </span>
  );
}

function DetailView({ signal, onBack }: { signal: GeoSignal; onBack: () => void }) {
  const checkpoints = ["+1h", "+6h", "+1d", "+3d", "+7d"];
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
          style={{ fontFamily: "Fraunces, serif", fontWeight: 500, letterSpacing: "-0.01em" }}
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
            Affected tickers
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {signal.tickers.length === 0 ? (
              <span className="text-[12px] text-[rgba(31,27,22,0.5)]">None tagged</span>
            ) : (
              signal.tickers.map((t) => (
                <span
                  key={t}
                  className="rounded-full px-2.5 py-1 text-[11px]"
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    color: "#9A6B1F",
                    backgroundColor: "rgba(154,107,31,0.10)",
                  }}
                >
                  {t}
                </span>
              ))
            )}
          </div>
        </div>

        <div className="mt-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(31,27,22,0.5)]">
            Checkpoints
          </p>
          <div className="mt-4 relative">
            <div className="absolute left-0 right-0 top-[7px] h-px bg-[rgba(31,27,22,0.14)]" />
            <div className="relative flex justify-between">
              {checkpoints.map((c) => (
                <div key={c} className="flex flex-col items-center gap-2">
                  <span
                    className="h-3.5 w-3.5 rounded-full border border-[rgba(31,27,22,0.25)] bg-[#FEFCF5]"
                  />
                  <span
                    className="text-[10px] text-[rgba(31,27,22,0.6)]"
                    style={{ fontFamily: "JetBrains Mono, monospace" }}
                  >
                    {c}
                  </span>
                </div>
              ))}
            </div>
            <p className="mt-3 text-[11px] text-[rgba(31,27,22,0.5)]">
              Outcome tracking pending — checkpoints fill in as the signal ages.
            </p>
          </div>
        </div>
      </div>
      <div className="border-t border-[rgba(31,27,22,0.14)] px-5 py-3">
        <p
          className="text-[10px] text-[rgba(31,27,22,0.5)]"
          style={{ fontFamily: "JetBrains Mono, monospace" }}
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
        style={{ fontFamily: "JetBrains Mono, monospace", color: valueColor }}
      >
        {value}
      </p>
    </div>
  );
}