/**
 * Turn a failed API response into an Error carrying a message worth showing.
 *
 * The backend already writes readable Spanish for anything a user can trigger
 * ("Solo se aceptan archivos PDF"). Callers used to surface the raw body, so an
 * import toast read:
 *
 *   Import error: {"detail":"Solo se aceptan archivos PDF"}
 *
 * Pull the detail out and leave the JSON envelope in the network tab, where it
 * belongs. Kept in its own module so it can be tested without importing the API
 * client, which pulls in next-auth.
 */
export async function apiError(res: Response): Promise<Error> {
  return errorFromBody(await res.text(), res.status);
}

/** Exposed for tests; `apiError` is the wrapper callers use. */
export function errorFromBody(body: string, status: number): Error {
  try {
    const detail = (JSON.parse(body) as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) {
      return new Error(detail.trim());
    }
    // FastAPI request-validation errors put a list of {loc, msg} under detail.
    if (Array.isArray(detail)) {
      const msg = detail
        .map((d) => (d as { msg?: string })?.msg)
        .filter((m): m is string => typeof m === "string" && m.trim() !== "")
        .join("; ");
      if (msg) return new Error(msg);
    }
  } catch {
    // Not JSON (proxy error page, empty body) — fall through to the raw text.
  }
  return new Error(body.trim() || `Error ${status}`);
}
