"use client";

import { useState } from "react";
import Link from "next/link";
import { signOut } from "next-auth/react";
import { Download, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * The user's data rights, exercisable without writing to anyone: download
 * everything FinView stores (GDPR arts. 15 and 20) and erase the account
 * (art. 17). Deletion asks for the password again because the session lasts 90
 * days, and is final — the copy says so before the button is enabled.
 */
export function AccountDataRights() {
  const [exporting, setExporting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      await api.me.exportData();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudieron descargar tus datos.");
    } finally {
      setExporting(false);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await api.me.deleteAccount(password);
      await signOut({ callbackUrl: "/" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar la cuenta.");
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-4 border-t pt-4 text-sm">
      <div className="flex flex-wrap gap-3">
        <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
          <Download className="mr-2 h-4 w-4" />
          {exporting ? "Preparando..." : "Descargar mis datos"}
        </Button>
        {!confirming && (
          <Button variant="outline" size="sm" onClick={() => setConfirming(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            Eliminar cuenta
          </Button>
        )}
      </div>

      {confirming && (
        <div className="space-y-3 rounded-lg border border-destructive/40 p-4">
          <p>
            Se borrarán de forma <strong>inmediata e irreversible</strong> tu cuenta, tus
            importaciones, operaciones, cálculos fiscales y listas de seguimiento. Descarga antes tus datos si
            quieres conservarlos.
          </p>
          <Input
            type="password"
            placeholder="Tu contraseña"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="max-w-xs"
          />
          <div className="flex gap-3">
            <Button
              variant="destructive"
              size="sm"
              onClick={handleDelete}
              disabled={deleting || password.length === 0}
            >
              {deleting ? "Eliminando..." : "Eliminar definitivamente"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setConfirming(false);
                setPassword("");
                setError(null);
              }}
              disabled={deleting}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {error && <p className="text-destructive">{error}</p>}

      <p className="text-xs text-muted-foreground">
        <Link href="/legal/condiciones" className="underline underline-offset-2">Condiciones</Link>
        {" · "}
        <Link href="/legal/privacidad" className="underline underline-offset-2">Privacidad</Link>
        {" · "}
        <Link href="/legal/cookies" className="underline underline-offset-2">Cookies</Link>
        {" · "}
        <Link href="/legal/aviso-legal" className="underline underline-offset-2">Aviso legal</Link>
      </p>
    </div>
  );
}
