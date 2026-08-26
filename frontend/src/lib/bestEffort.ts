/**
 * Swallow a failed enrichment fetch, but leave a trace.
 *
 * Eleven fetches across the options, portfolio, zonas-clave and geo-intel pages
 * ended in a bare `.catch(() => {})`. Degrading silently is right for most of
 * them — they load cross-page badges, lens toggles and autocomplete
 * suggestions, and an error banner because a badge could not load would be
 * worse than the missing badge. What was wrong is that a persistent failure
 * left no trace anywhere, so nobody debugging "why is the Ideas link never
 * showing" had anything to go on.
 *
 * `console.warn` rather than `console.error` on purpose: these are degradations,
 * not the page failing. The dashboard's primary loads use `console.error`, and
 * the two should stay distinguishable in a console.
 *
 * Use this only where the page is genuinely fine without the data. A fetch whose
 * absence the user would misread as "you have none" needs a real error state,
 * not this.
 */
export function bestEffort(label: string) {
  return (error: unknown): void => {
    console.warn(`[best-effort] ${label}:`, error);
  };
}
