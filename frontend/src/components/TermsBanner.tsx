"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { Button } from "@/components/ui/button";

/**
 * Asks a signed-in user to accept the current terms and privacy policy.
 *
 * New accounts accept at sign-up. This covers the two other cases: accounts
 * created before acceptance was recorded, and everyone after a new version of
 * the documents is published. Renders nothing once accepted, and nothing if the
 * check itself fails or the backend does not report the field yet (the two
 * halves deploy separately) — a banner nobody can dismiss would be worse than
 * a late acceptance.
 */
export function TermsBanner() {
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.me
      .get()
      .then((me) => setPending(me.terms_accepted === false))
      .catch(bestEffort("terms acceptance check"));
  }, []);

  if (!pending) return null;

  async function accept() {
    setSaving(true);
    try {
      await api.me.acceptTerms();
      setPending(false);
    } catch (error) {
      bestEffort("terms acceptance")(error);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4 text-sm">
      <p>
        Hemos publicado las{" "}
        <Link href="/legal/condiciones" className="underline underline-offset-2">
          Condiciones de uso
        </Link>{" "}
        y la{" "}
        <Link href="/legal/privacidad" className="underline underline-offset-2">
          Política de privacidad
        </Link>
        . Para seguir usando FinView, revísalas y acéptalas.
      </p>
      <Button size="sm" onClick={accept} disabled={saving}>
        {saving ? "Guardando..." : "Aceptar"}
      </Button>
    </div>
  );
}
