import type { TechnicalSignal } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

/**
 * Small presentational badges shared by the Monitor tab's panels.
 *
 * Pure render, no state: they read one value and pick a variant/colour/title.
 * Moved out of page.tsx unchanged.
 */

export function severityColor(s: string) {
  switch (s) {
    case "HIGH":
      return "destructive";
    case "MEDIUM":
      return "secondary";
    default:
      return "outline";
  }
}

export function DirBadge({ direction }: { direction: "BULLISH" | "BEARISH" }) {
  const bullish = direction === "BULLISH";
  return (
    <Badge
      variant="outline"
      className={`text-xs ${
        bullish
          ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600"
          : "border-red-500/20 bg-red-500/10 text-red-600"
      }`}
      title={
        bullish
          ? "El precio se acerca a la zona por debajo: romperla sería al alza"
          : "El precio se acerca a la zona por encima: romperla sería a la baja"
      }
    >
      {bullish ? "↑ Alcista" : "↓ Bajista"}
    </Badge>
  );
}

export function BreakProbability({ signal }: { signal: TechnicalSignal }) {
  // null means the model couldn't score it — never render that as 0%, which
  // would read as "certainly won't break" rather than "we don't know".
  if (signal.break_probability == null) {
    return (
      <Badge variant="outline" className="text-xs text-muted-foreground" title="El modelo no pudo puntuar esta señal">
        sin puntuar
      </Badge>
    );
  }
  return (
    <Badge
      variant={signal.alerted ? "destructive" : "outline"}
      className="text-xs tabular-nums"
      title={
        signal.alerted
          ? "Supera el umbral de alerta (70%), que es provisional y no está calibrado"
          : "Por debajo del umbral de alerta (70%). Se guarda igual, para poder calibrarlo"
      }
    >
      {signal.break_probability}%
    </Badge>
  );
}

/** Macro-regime alignment tag for an alert (Phase 2b, informational only). */
export function AlignmentTag({ alignment }: { alignment?: string | null }) {
  if (!alignment || alignment === "neutral") return null;
  const aligned = alignment === "aligned";
  const color = aligned
    ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
    : "bg-amber-500/10 text-amber-600 border-amber-500/20";
  return (
    <Badge
      variant="outline"
      className={`text-xs ${color}`}
      title={
        aligned
          ? "A favor del régimen macro (informativo — no cambia la señal)"
          : "En contra del régimen macro (informativo — no cambia la señal)"
      }
    >
      {aligned ? "macro ✓" : "macro ✗"}
    </Badge>
  );
}
