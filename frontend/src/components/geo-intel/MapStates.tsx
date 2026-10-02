export function MapLoading() {
  return (
    <div className="flex h-full w-full items-center justify-center">
      <style>{`
        @keyframes mapDot { 0%,100% { opacity: 0.25; transform: scale(1); } 50% { opacity: 0.7; transform: scale(1.4); } }
      `}</style>
      <span
        className="h-3 w-3 rounded-full bg-primary"
        style={{ animation: "mapDot 1.8s cubic-bezier(0.2,0.8,0.2,1) infinite" }}
      />
    </div>
  );
}

export function MapEmpty() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 text-foreground/60">
      <CompassGlyph />
      <p className="text-[13px]">No signals in view</p>
    </div>
  );
}

export function MapError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-full w-full items-center justify-center p-6">
      <div className="max-w-xs rounded-xl border border-foreground/14 bg-card px-5 py-4 text-center shadow-[var(--fv-shadow-md)]">
        <p className="text-[13px] text-foreground">Couldn&apos;t load signals</p>
        <p className="mt-1 text-[11px] text-foreground/60">
          The feed didn&apos;t respond. You can try again.
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 inline-flex h-7 items-center rounded-md border border-primary bg-transparent px-3 text-[11px] text-primary transition-colors hover:bg-primary/8"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

export function ListSkeleton() {
  return (
    <div className="divide-y divide-foreground/8">
      <style>{`
        @keyframes skel { 0%,100% { opacity: 0.5; } 50% { opacity: 0.85; } }
        .skel { animation: skel 1.6s ease-in-out infinite; background-color: color-mix(in srgb, var(--fv-ink) 8%, transparent); border-radius: 4px; }
      `}</style>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-start gap-3 px-5 py-3">
          <div className="skel mt-1.5 h-2 w-2 rounded-full" />
          <div className="flex-1 space-y-1.5">
            <div className="skel h-3 w-4/5" />
            <div className="skel h-2 w-2/5" />
          </div>
          <div className="skel h-3 w-6" />
        </div>
      ))}
    </div>
  );
}

function CompassGlyph() {
  return (
    <svg width="36" height="36" viewBox="0 0 36 36" fill="none" aria-hidden>
      <circle
        cx="18"
        cy="18"
        r="15"
        stroke="color-mix(in srgb, var(--fv-ink) 35%, transparent)"
        strokeWidth="0.8"
        fill="none"
      />
      <circle
        cx="18"
        cy="18"
        r="9"
        stroke="color-mix(in srgb, var(--fv-ink) 25%, transparent)"
        strokeWidth="0.6"
        fill="none"
      />
      <path
        d="M18 4 L18 32 M4 18 L32 18"
        stroke="color-mix(in srgb, var(--fv-ink) 25%, transparent)"
        strokeWidth="0.6"
      />
      <path
        d="M18 8 L20 18 L18 28 L16 18 Z"
        fill="color-mix(in srgb, var(--fv-ochre) 50%, transparent)"
        stroke="var(--fv-ochre)"
        strokeWidth="0.6"
      />
    </svg>
  );
}