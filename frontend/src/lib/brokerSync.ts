/**
 * IBKR sync, as the browser drives it.
 *
 * The backend imports at most one year per request (production work must fit
 * inside one), so the browser keeps calling `POST /brokers/ibkr/sync` while the
 * state is "running". These are the pure parts of that loop: what to show and
 * how long to wait before the next step.
 */

export interface BrokerConnection {
  enabled: boolean;
  connected: boolean;
  query_id?: string | null;
  token_hint?: string | null;
  account_opened_on?: string | null;
  history_pending?: boolean;
  last_synced_at?: string | null;
  last_error?: string | null;
  in_progress?: boolean;
  gaps?: Record<string, string>;
}

export type SyncState = "running" | "done" | "error";

export interface SyncProgress {
  state: SyncState;
  done: number;
  total: number;
  year: number | null;
  message: string | null;
  gaps: Record<string, string>;
  retry_after: number;
}

/**
 * Consecutive steps that only waited on IBKR before the browser stops asking
 * (~5 minutes: each such step polls for up to 20 s server-side, then waits
 * 5 s here). The run is kept on the server, so the next sync resumes it;
 * without a cap a stuck statement would poll for as long as the tab is open.
 */
export const MAX_WAITING_STEPS = 12;

/** A step that imported something is followed at once; a waiting one is not. */
const NEXT_STEP_MS = 500;

/**
 * Delay before the next step. A step that carries a message is waiting on IBKR
 * (statement still generating, request limit), and asking again at once would
 * only spend its 10-per-minute allowance.
 */
export function nextStepDelayMs(progress: SyncProgress): number {
  return progress.message ? progress.retry_after * 1000 : NEXT_STEP_MS;
}

export function progressLabel(progress: SyncProgress): string {
  if (progress.state === "done") {
    return progress.total === 1
      ? "Sincronización completa"
      : `Sincronización completa: ${progress.done} años`;
  }
  if (progress.state === "error") return progress.message ?? "La sincronización se detuvo";
  const year = progress.year ? ` (${progress.year})` : "";
  return `Importando ${Math.min(progress.done + 1, progress.total)} de ${progress.total}${year}`;
}

/** Years IBKR could not provide, oldest first; the history note goes last. */
export function gapLines(gaps: Record<string, string> | undefined): string[] {
  const entries = Object.entries(gaps ?? {});
  const years = entries
    .filter(([key]) => /^\d{4}$/.test(key))
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([year, reason]) => `${year}: ${reason}`);
  const notes = entries.filter(([key]) => !/^\d{4}$/.test(key)).map(([, reason]) => reason);
  return [...years, ...notes];
}
