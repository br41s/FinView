/**
 * Canonical public origin, shared by the metadata, sitemap and robots routes.
 *
 * Resolution order:
 *   1. NEXT_PUBLIC_SITE_URL — set this when the site moves to its own domain.
 *   2. VERCEL_PROJECT_PRODUCTION_URL — injected by Vercel on production builds,
 *      so previews still emit absolute URLs pointing at production rather than
 *      at the ephemeral preview host.
 *   3. The current production deployment, as a last resort.
 *
 * Always returned without a trailing slash so callers can concatenate paths.
 */
const FALLBACK_ORIGIN = "https://fin-view-topaz.vercel.app";

function resolveSiteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return explicit.replace(/\/+$/, "");

  const vercel = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (vercel) return `https://${vercel}`.replace(/\/+$/, "");

  return FALLBACK_ORIGIN;
}

export const SITE_URL = resolveSiteUrl();

/** Route prefixes that require a session — excluded from search indexing. */
export const PRIVATE_ROUTES = [
  "/accounts",
  "/alt-investments",
  "/api",
  "/billing",
  "/dashboard",
  "/geo-intel",
  "/options",
  "/portfolio",
  "/zonas-clave",
] as const;
