import Link from "next/link";

/**
 * Notice shown on every screen that renders machine-generated market signals
 * (Options, Zonas Clave, Ideas).
 *
 * Two obligations meet here: AI-generated text must be recognisable as such
 * (EU AI Act, art. 50), and FinView is not an authorised investment firm, so
 * its signals must not read as personal recommendations. One component keeps
 * the wording identical on all three screens and in step with /legal/condiciones.
 */
export function AiDisclaimer() {
  return (
    <p className="text-xs text-muted-foreground/80">
      Señales y textos generados automáticamente, en parte por IA. Son información, no una
      recomendación de inversión, y no tienen en cuenta tu situación personal.{" "}
      <Link href="/legal/condiciones" className="underline underline-offset-2">
        Más información
      </Link>
    </p>
  );
}
