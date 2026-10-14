/**
 * When to renew the backend token.
 *
 * The backend JWT lives 90 days from login and is only minted at login, while
 * the NextAuth cookie rolls forward on activity, so a session can outlive its
 * token (production, 2026-10-14). The `jwt` callback in auth.ts asks the
 * backend for a fresh one once fewer than REFRESH_WINDOW_SECONDS remain. Pure
 * and framework-free so it can be unit tested; nothing here verifies the
 * token, the backend does that.
 */

export const REFRESH_WINDOW_SECONDS = 7 * 24 * 60 * 60;

/** The `exp` claim of a JWT in seconds since the epoch, or 0 when unreadable. */
export function decodeExp(token: string): number {
  try {
    const payload = token.split(".")[1] ?? "";
    // JWT segments are base64url: atob wants plain base64 with padding.
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const claims = JSON.parse(atob(padded)) as { exp?: unknown };
    return typeof claims.exp === "number" ? claims.exp : 0;
  } catch {
    return 0;
  }
}

/**
 * True when the token is readable and expires within the window. An
 * unreadable expiry is never refreshed: the backend will reject the token if
 * it is bad, and request() signs the session out on the refused retry.
 */
export function shouldRefresh(
  exp: number,
  nowSeconds: number,
  windowSeconds = REFRESH_WINDOW_SECONDS,
): boolean {
  return exp > 0 && exp - nowSeconds < windowSeconds;
}
