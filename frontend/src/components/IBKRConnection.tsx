"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Loader2, Link2, RefreshCw, Unplug, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { fmtDateTime } from "@/lib/format";
import {
  MAX_WAITING_STEPS,
  gapLines,
  nextStepDelayMs,
  progressLabel,
  type BrokerConnection,
  type SyncProgress,
} from "@/lib/brokerSync";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Direct IBKR connection through a read-only Flex token.
 *
 * Renders nothing when the backend has no encryption key configured: the
 * feature is off there, and a card that can only say "no disponible" is noise.
 */
export function IBKRConnection({ onSynced }: { onSynced: () => void }) {
  const [conn, setConn] = useState<BrokerConnection | null>(null);
  const [editing, setEditing] = useState(false);
  const [token, setToken] = useState("");
  const [queryId, setQueryId] = useState("");
  const [fullHistory, setFullHistory] = useState(true);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<SyncProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const reloadConnection = useCallback(() => {
    api.ibkr
      .get()
      .then((c) => {
        if (alive.current) setConn(c);
      })
      .catch(bestEffort("IBKR connection"));
  }, []);

  useEffect(() => {
    alive.current = true;
    reloadConnection();
    return () => {
      alive.current = false;
    };
  }, [reloadConnection]);

  // The backend imports one year per request; keep stepping while it says "running".
  // Leaving the page stops the loop, and the next sync resumes where it stopped.
  const runSync = useCallback(async () => {
    setBusy(true);
    setError(null);
    setProgress(null);
    try {
      let waiting = 0;
      for (;;) {
        const step = await api.ibkr.sync();
        if (!alive.current) return;
        setProgress(step);
        if (step.state === "done") {
          if (gapLines(step.gaps).length > 0) {
            toast.warning("Sincronización terminada con años sin importar", {
              description: progressLabel(step),
            });
          } else {
            toast.success("IBKR sincronizado", { description: progressLabel(step) });
          }
          onSynced();
          break;
        }
        if (step.state === "error") {
          toast.error("La sincronización con IBKR se detuvo", {
            description: step.message ?? undefined,
          });
          break;
        }
        waiting = step.message ? waiting + 1 : 0;
        if (waiting >= MAX_WAITING_STEPS) {
          setError(
            "IBKR sigue sin entregar el informe. Vuelve a sincronizar más tarde: se retomará donde quedó.",
          );
          break;
        }
        await wait(nextStepDelayMs(step));
        if (!alive.current) return;
      }
    } catch (err: unknown) {
      if (alive.current) setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      if (alive.current) {
        setBusy(false);
        reloadConnection();
      }
    }
  }, [onSynced, reloadConnection]);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.ibkr.connect({
        token: token.trim(),
        query_id: queryId.trim(),
        full_history: fullHistory,
      });
      setConn(saved);
      setToken("");
      setEditing(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error desconocido");
      setBusy(false);
      return;
    }
    await runSync();
  };

  const disconnect = async () => {
    if (
      !window.confirm(
        "¿Desconectar IBKR? Se borra el token guardado; los datos ya importados se conservan.",
      )
    ) {
      return;
    }
    try {
      await api.ibkr.disconnect();
      setProgress(null);
      reloadConnection();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    }
  };

  if (!conn?.enabled) return null;

  const showForm = !conn.connected || editing;
  const gaps = gapLines(progress?.gaps ?? conn.gaps);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Link2 className="h-4 w-4" />
          Conexión directa con IBKR
        </CardTitle>
        <CardDescription>
          FinView descarga tus extractos con un token Flex de solo lectura: no puede operar ni
          mover dinero. El token se guarda cifrado y nunca se vuelve a mostrar.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {showForm ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              void connect();
            }}
          >
            <details className="rounded-md border border-border p-3 text-muted-foreground">
              <summary className="cursor-pointer text-foreground">
                Cómo crear la consulta y el token en IBKR
              </summary>
              <ol className="mt-2 list-decimal space-y-1 pl-5">
                <li>
                  En el Portal de Clientes, ve a Performance &amp; Reports → Flex Queries y crea
                  una <strong>Activity Flex Query</strong> para una sola cuenta.
                </li>
                <li>
                  Incluye las secciones Account Information (con <em>Date Opened</em>), Trades
                  (Executions), Open Positions, Cash Transactions y Realized and Unrealized
                  Performance Summary in Base.
                </li>
                <li>
                  En cada sección, selecciona <strong>todos los campos</strong>; en Trades, el nivel
                  Execution, y en Cash Transactions, Detail.
                </li>
                <li>
                  Formato <strong>XML</strong> y fecha <strong>yyyyMMdd</strong>. Guarda y anota el
                  número de la consulta (Query ID).
                </li>
                <li>
                  En Flex Web Service Configuration, activa el servicio y genera un token sin
                  restricción de IP. Elige la caducidad más larga (hasta un año).
                </li>
              </ol>
            </details>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ibkr-token">Token Flex</Label>
                <Input
                  id="ibkr-token"
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ibkr-query">Query ID</Label>
                <Input
                  id="ibkr-query"
                  inputMode="numeric"
                  autoComplete="off"
                  value={queryId}
                  onChange={(e) => setQueryId(e.target.value)}
                  required
                />
              </div>
            </div>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={fullHistory}
                onChange={(e) => setFullHistory(e.target.checked)}
              />
              <span>
                Traer todo el historial desde la apertura de la cuenta (recomendado).
                <span className="block text-muted-foreground">
                  Cada año sincronizado sustituye al archivo de IBKR que hubieras subido para ese
                  año.
                </span>
              </span>
            </label>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" size="sm" disabled={busy || !token.trim() || !queryId.trim()}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                Conectar y sincronizar
              </Button>
              {editing && (
                <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
                  Cancelar
                </Button>
              )}
            </div>
          </form>
        ) : (
          <>
            <p className="text-muted-foreground">
              Query {conn.query_id} · token ····{conn.token_hint}
              {conn.last_synced_at
                ? ` · Última sincronización: ${fmtDateTime(conn.last_synced_at)}`
                : " · Aún no sincronizado"}
            </p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={() => void runSync()} disabled={busy}>
                {busy ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {conn.in_progress ? "Continuar sincronización" : "Sincronizar ahora"}
              </Button>
              <Button variant="outline" size="sm" onClick={() => setEditing(true)} disabled={busy}>
                <KeyRound className="h-4 w-4" />
                Cambiar token
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void disconnect()} disabled={busy}>
                <Unplug className="h-4 w-4" />
                Desconectar
              </Button>
            </div>
          </>
        )}

        {busy && !progress && (
          <p className="text-muted-foreground">Conectando con IBKR…</p>
        )}
        {progress && (
          <p className={progress.state === "error" ? "text-destructive" : "text-muted-foreground"}>
            {progressLabel(progress)}
            {progress.state === "running" && progress.message ? ` — ${progress.message}` : ""}
          </p>
        )}
        {!progress && conn.last_error && <p className="text-destructive">{conn.last_error}</p>}
        {error && <p className="text-destructive">{error}</p>}
        {gaps.length > 0 && (
          <div className="rounded-md border border-border p-3">
            <p className="mb-1 font-medium">No se pudo importar:</p>
            <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
              {gaps.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
