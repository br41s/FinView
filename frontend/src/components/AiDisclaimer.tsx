import Link from "next/link";
import { NOT_ADVICE } from "@/lib/legal";

/**
 * Notice shown wherever FinView renders machine-generated signals or text:
 * the Options, Zonas Clave and Ideas headers, and again next to each LLM output
 * a user reads on its own (chat, reports, a signal's detail), because the page
 * header is out of view by then.
 *
 * Two obligations meet here: AI-generated text must be recognisable as such
 * (EU AI Act, art. 50), and FinView is a data tool, not an authorised adviser,
 * so nothing it shows may read as a recommendation. The wording lives in
 * `NOT_ADVICE` so every screen and /legal/condiciones say the same thing.
 */
export function AiDisclaimer({ className = "" }: { className?: string }) {
  return (
    <p className={`text-xs text-muted-foreground/80 ${className}`}>
      {NOT_ADVICE.signals}{" "}
      <Link href="/legal/condiciones" className="underline underline-offset-2">
        Más información
      </Link>
    </p>
  );
}

/** Caveat for hit rates and backtests. */
export function PastPerformanceNote({ className = "" }: { className?: string }) {
  return (
    <p className={`text-xs text-muted-foreground/80 ${className}`}>{NOT_ADVICE.pastPerformance}</p>
  );
}
