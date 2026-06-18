import type { GeoSignal } from "@/lib/geo";

export const CATEGORIES: GeoSignal["category"][] = [
  "earthquake",
  "cyclone",
  "fire",
  "volcano",
  "conflict",
  "maritime",
  "weather",
];

export type DirectionFilter = "all" | "bullish" | "bearish";

type Props = {
  categories: GeoSignal["category"][];
  onCategoriesChange: (next: GeoSignal["category"][]) => void;
  direction: DirectionFilter;
  onDirectionChange: (d: DirectionFilter) => void;
  activeOnly: boolean;
  onActiveOnlyChange: (v: boolean) => void;
};

const PILL_BASE =
  "h-7 rounded-md border px-2.5 text-[11px] capitalize transition-colors";
const PILL_OFF =
  "border-[rgba(31,27,22,0.14)] bg-transparent text-[rgba(31,27,22,0.7)] hover:bg-[rgba(154,107,31,0.06)]";
const PILL_ON = "border-[#9A6B1F] bg-[rgba(154,107,31,0.10)] text-[#825416]";

export function FilterBar({
  categories,
  onCategoriesChange,
  direction,
  onDirectionChange,
  activeOnly,
  onActiveOnlyChange,
}: Props) {
  const toggleCategory = (c: GeoSignal["category"]) => {
    onCategoriesChange(
      categories.includes(c)
        ? categories.filter((x) => x !== c)
        : [...categories, c],
    );
  };

  return (
    <div className="pointer-events-auto relative z-10 m-2 flex flex-wrap items-center gap-3 rounded-lg border border-[rgba(31,27,22,0.14)] bg-[#FEFCF5]/90 px-3 py-2 shadow-[0_4px_16px_rgba(31,27,22,0.08)] backdrop-blur lg:absolute lg:inset-x-4 lg:top-4 lg:m-0">
      <div className="flex flex-wrap gap-1">
        {CATEGORIES.map((c) => {
          const on = categories.includes(c);
          return (
            <button
              key={c}
              type="button"
              aria-pressed={on}
              onClick={() => toggleCategory(c)}
              className={`${PILL_BASE} ${on ? PILL_ON : PILL_OFF}`}
            >
              {c}
            </button>
          );
        })}
      </div>

      <div className="mx-1 h-5 w-px bg-[rgba(31,27,22,0.14)]" />

      <div className="flex gap-1">
        {(["all", "bullish", "bearish"] as DirectionFilter[]).map((d) => {
          const on = direction === d;
          return (
            <button
              key={d}
              type="button"
              aria-pressed={on}
              onClick={() => onDirectionChange(d)}
              className={`${PILL_BASE} ${on ? PILL_ON : PILL_OFF}`}
            >
              {d}
            </button>
          );
        })}
      </div>

      <div className="mx-1 h-5 w-px bg-[rgba(31,27,22,0.14)]" />

      <button
        type="button"
        role="switch"
        aria-checked={activeOnly}
        onClick={() => onActiveOnlyChange(!activeOnly)}
        className="flex items-center gap-2 text-[11px] text-[rgba(31,27,22,0.7)]"
      >
        <span
          className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
            activeOnly ? "bg-[#9A6B1F]" : "bg-[rgba(31,27,22,0.2)]"
          }`}
        >
          <span
            className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
              activeOnly ? "translate-x-3.5" : "translate-x-0.5"
            }`}
          />
        </span>
        Active only
      </button>
    </div>
  );
}
