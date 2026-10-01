/**
 * Is the Ideas pipeline alive?
 *
 * The page used to answer this with the date of the newest signal, which cannot
 * tell a stopped pipeline from a quiet week — and that ambiguity is exactly how
 * Ideas sat dead for six weeks looking merely calm. The backend now records
 * every cycle (`GET /geo/scheduler/status` → `last_run`), so the question has a
 * real answer: when it last ran, whether it finished, and what it ingested.
 *
 * Pure on purpose: `now` is injected so the thresholds are testable.
 */

export interface GeoCycleRun {
  started_at: string;
  finished_at: string;
  ok: boolean;
  events: number;
  new_signals: number;
  /** Signals that reached at least one channel (ntfy / Telegram / email). */
  notified: number;
  /** Signals the notify gate selected that no channel delivered. */
  notify_failed?: number;
  checkpoints_evaluated: number;
  persist_failures: number;
  sources: Record<string, number>;
  error: string | null;
}

export interface GeoHealthInput {
  interval_minutes: number;
  last_run?: GeoCycleRun | null;
}

export type GeoHealthTone = "ok" | "warn" | "down";

export interface GeoHealth {
  tone: GeoHealthTone;
  message: string;
}

/** Cycles missed before the silence stops being normal. */
const MISSED_CYCLES = 3;
/** Floor for the staleness window: three missed cycles of the hourly prod cron.
 *  The in-process interval reported here is 15, so three of those alone would
 *  warn after a single missed hourly cycle. */
const MIN_STALE_MINUTES = 180;
/** Beyond this, "late" is not a plausible reading any more. */
const DOWN_AFTER_MINUTES = 24 * 60;

const MINUTE = 60_000;

export function formatAge(ms: number): string {
  const minutes = Math.floor(ms / MINUTE);
  if (minutes < 1) return "hace menos de un minuto";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  return `hace ${days} ${days === 1 ? "día" : "días"}`;
}

export function geoHealth(
  status: GeoHealthInput | null,
  now: number = Date.now(),
): GeoHealth | null {
  if (!status) return null;

  const run = status.last_run;
  if (!run) {
    return {
      tone: "warn",
      message:
        "Sin ejecuciones registradas todavía. Si esto no cambia, el cron de " +
        "producción no está llamando a /api/geo/cron.",
    };
  }

  const age = now - new Date(run.started_at).getTime();
  const ageText = formatAge(age);

  if (!run.ok) {
    const detail = run.error ? ` (${run.error})` : "";
    return {
      tone: "down",
      message: `La última ejecución (${ageText}) falló${detail}. Ideas no está produciendo señales.`,
    };
  }

  const staleAfter =
    Math.max(status.interval_minutes * MISSED_CYCLES, MIN_STALE_MINUTES) * MINUTE;
  if (age > DOWN_AFTER_MINUTES * MINUTE) {
    return {
      tone: "down",
      message: `El pipeline no se ejecuta desde ${ageText}. Revisa el job geo-intel-cycle de Cloud Scheduler.`,
    };
  }
  if (age > staleAfter) {
    return {
      tone: "warn",
      message: `Última ejecución ${ageText}; se esperaba una más reciente. El cron puede estar parado.`,
    };
  }

  // A cycle that ingests nothing from any source is not a calm world: no quiet
  // day leaves USGS, EONET and GDELT simultaneously empty. It means egress or
  // credentials, and it looks identical to "no news" everywhere else in the UI.
  const counts = Object.values(run.sources ?? {});
  if (counts.length > 0 && counts.every((n) => n === 0)) {
    return {
      tone: "warn",
      message: `La última ejecución (${ageText}) no recibió nada de ninguna fuente. Comprueba la salida de red y las claves de ingesta.`,
    };
  }

  // Lost work outranks a missed push: a signal the persist phase dropped is
  // gone, an undelivered alert is retried next cycle.
  if (run.persist_failures > 0) {
    return {
      tone: "warn",
      message: `La última ejecución (${ageText}) descartó ${run.persist_failures} señal${
        run.persist_failures === 1 ? "" : "es"
      } al guardarlas.`,
    };
  }

  // A run that selected alerts and delivered none is a delivery outage. It is
  // invisible in every other field: `notified` at zero reads exactly like a
  // cycle where nothing crossed the gate.
  const undelivered = run.notify_failed ?? 0;
  if (undelivered > 0) {
    return {
      tone: "warn",
      message: `La última ejecución (${ageText}): ${undelivered} alerta${
        undelivered === 1 ? "" : "s"
      } no entregada${
        undelivered === 1 ? "" : "s"
      }. Revisa las claves de ntfy, Telegram y email.`,
    };
  }

  // Deliveries are only mentioned when there were any: a healthy cycle that
  // matched nothing shouldn't read as "0 notificadas".
  const delivered =
    run.notified > 0
      ? ` · ${run.notified} notificada${run.notified === 1 ? "" : "s"}`
      : "";
  return {
    tone: "ok",
    message: `Última ejecución ${ageText} · ${run.events} eventos · ${run.new_signals} señales nuevas${delivered}`,
  };
}
