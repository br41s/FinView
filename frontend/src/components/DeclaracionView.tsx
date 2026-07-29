"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatEur } from "@/lib/format";
import type {
  FiscalProfile,
  ManualSavingsIncome,
  SavingsEstimate,
} from "@/lib/types";

const CATEGORY_LABEL: Record<ManualSavingsIncome["category"], string> = {
  INTEREST: "Intereses (casilla 0027)",
  DIVIDEND: "Dividendos (casilla 0029)",
  GAIN: "Ganancia patrimonial",
  LOSS: "Pérdida patrimonial",
  RCM: "Intereses / dividendos", // legacy entries
};

export function DeclaracionView({ fiscalYear }: { fiscalYear: number }) {
  const [profile, setProfile] = useState<FiscalProfile | null>(null);
  const [manual, setManual] = useState<ManualSavingsIncome[]>([]);
  const [estimate, setEstimate] = useState<SavingsEstimate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    const [p, m, e] = await Promise.all([
      api.fiscalProfile(fiscalYear) as Promise<FiscalProfile>,
      api.manualIncome(fiscalYear) as Promise<ManualSavingsIncome[]>,
      api.savingsEstimate(fiscalYear),
    ]);
    setProfile(p);
    setManual(m);
    setEstimate(e);
  }, [fiscalYear]);

  useEffect(() => {
    setLoading(true);
    refresh().finally(() => setLoading(false));
  }, [refresh]);

  async function saveProfile() {
    if (!profile) return;
    setSaving(true);
    try {
      await api.saveFiscalProfile(fiscalYear, {
        age: profile.age,
        disability: profile.disability,
        descendants: profile.descendants,
        general_base: profile.general_base,
        prior_rcm_loss: profile.prior_rcm_loss,
        prior_gp_loss: profile.prior_gp_loss,
      });
      await refresh();
    } finally {
      setSaving(false);
    }
  }

  if (loading || !profile || !estimate) {
    return <p className="text-muted-foreground text-sm">Cargando estimación…</p>;
  }

  const ratesMismatch = estimate.rates_year_used !== fiscalYear;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      {/* Left: questionnaire */}
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Tus datos {fiscalYear}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Field label="Edad">
              <Input
                type="number"
                value={profile.age ?? ""}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    age: e.target.value === "" ? null : Number(e.target.value),
                  })
                }
                className="max-w-[120px]"
              />
            </Field>

            <Field label="Discapacidad">
              <select
                value={profile.disability ?? ""}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    disability: (e.target.value || null) as FiscalProfile["disability"],
                  })
                }
                className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
              >
                <option value="">Ninguna</option>
                <option value="general">Entre 33% y 65%</option>
                <option value="severe">65% o más</option>
              </select>
            </Field>

            <Field label="Hijos / descendientes a cargo">
              <Input
                type="number"
                min={0}
                value={profile.descendants}
                onChange={(e) =>
                  setProfile({ ...profile, descendants: Math.max(0, Number(e.target.value)) })
                }
                className="max-w-[120px]"
              />
            </Field>

            <Field label="Rentas del trabajo / base general (€)">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={profile.general_base}
                onChange={(e) =>
                  setProfile({ ...profile, general_base: e.target.value || "0" })
                }
                className="max-w-[180px]"
              />
            </Field>
            <p className="text-xs text-muted-foreground">
              El mínimo personal y familiar se aplica primero sobre la base general;
              solo el resto reduce la base del ahorro. Si no tienes nómina, déjalo en 0.
            </p>

            <Field label="Pérdidas patrimoniales de años anteriores (€)">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={profile.prior_gp_loss}
                onChange={(e) =>
                  setProfile({ ...profile, prior_gp_loss: e.target.value || "0" })
                }
                className="max-w-[180px]"
              />
            </Field>
            <Field label="Pérdidas de RCM de años anteriores (€)">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={profile.prior_rcm_loss}
                onChange={(e) =>
                  setProfile({ ...profile, prior_rcm_loss: e.target.value || "0" })
                }
                className="max-w-[180px]"
              />
            </Field>
            <p className="text-xs text-muted-foreground">
              Saldos negativos pendientes de tus declaraciones de los 4 años anteriores.
              Compensan las ganancias del mismo tipo de este año (art. 49).
            </p>

            <Button onClick={saveProfile} disabled={saving} size="sm">
              {saving ? "Guardando…" : "Guardar y recalcular"}
            </Button>
          </CardContent>
        </Card>

        <ManualIncomeCard
          fiscalYear={fiscalYear}
          manual={manual}
          onChanged={refresh}
        />
      </div>

      {/* Right: result */}
      <div className="space-y-4">
        <Card className="sticky top-4">
          <CardHeader>
            <CardTitle>Estimación del ahorro</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Row label="RCM (intereses + dividendos)" value={estimate.rcm_net} />
            <Row label="Ganancias / pérdidas netas" value={estimate.gp_net} />
            {(Number(estimate.prior_gp_loss_applied) > 0 ||
              Number(estimate.prior_rcm_loss_applied) > 0) && (
              <Row
                label="Pérdidas años anteriores aplicadas"
                value={`-${(
                  Number(estimate.prior_gp_loss_applied) +
                  Number(estimate.prior_rcm_loss_applied)
                ).toFixed(2)}`}
                muted
              />
            )}
            <Row label="Base imponible del ahorro" value={estimate.savings_base} strong />
            <hr className="border-border" />
            <Row label="Mínimo personal y familiar" value={estimate.personal_minimum} muted />
            <Row label="Mínimo aplicado al ahorro" value={estimate.minimum_on_savings} muted />
            <Row label="Cuota íntegra del ahorro" value={estimate.gross_quota} />
            <Row label="Cuota tras mínimo" value={estimate.quota} strong />
            <Row label="Retenido en efectivo" value={`-${estimate.cash_withholdings}`} muted />
            <Row label="Pago a cuenta ES (0597)" value={`-${estimate.domestic_withholdings}`} muted />
            <Row label="Doble imposición aplicada (0588)" value={`-${estimate.double_taxation_credit_applied}`} muted />
            <Row label="Total aplicado" value={`-${estimate.withholdings}`} muted />
            <hr className="border-border" />
            <ResultRow result={estimate.result} />

            {Number(estimate.savings_base) > 0 && (
              <p className="text-xs text-muted-foreground">
                Tipo efectivo sobre la base del ahorro:{" "}
                {(
                  (Number(estimate.quota) / Number(estimate.savings_base)) *
                  100
                ).toLocaleString("es-ES", { maximumFractionDigits: 2 })}
                %
              </p>
            )}

            {estimate.brackets.length > 0 && (
              <details className="text-xs">
                <summary className="cursor-pointer text-muted-foreground">
                  Desglose por tramos
                </summary>
                <ul className="mt-1 space-y-0.5">
                  {estimate.brackets.map((b, i) => (
                    <li key={i} className="flex justify-between gap-2 tabular-nums">
                      <span className="text-muted-foreground">
                        {formatEur(b.from)}–{formatEur(b.to)} ·{" "}
                        {(Number(b.rate) * 100).toLocaleString("es-ES", {
                          maximumFractionDigits: 1,
                        })}
                        %
                      </span>
                      <span className="fv-sensitive">{formatEur(b.tax)}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {Number(estimate.gp_carryforward) < 0 && (
              <p className="text-xs text-muted-foreground">
                Pérdidas a compensar en ejercicios futuros:{" "}
                {formatEur(estimate.gp_carryforward)}.
              </p>
            )}

            {ratesMismatch && (
              <p className="text-xs text-amber-600 dark:text-amber-500">
                ⚠️ No hay tablas fiscales para {fiscalYear}; se han usado las de{" "}
                {estimate.rates_year_used}.
              </p>
            )}
            {!estimate.withholding_breakdown_complete && (
              <p className="text-xs text-amber-600 dark:text-amber-500">
                ⚠️ {estimate.incomplete_withholding_transactions} retenciones antiguas no
                tienen desglose origen/destino. Se muestran en el efectivo retenido, pero no
                reducen esta estimación hasta volver a importar el informe.
              </p>
            )}
            <p className="text-xs text-muted-foreground border-t border-border pt-2">
              Estimación orientativa de la base del ahorro. No es asesoramiento
              fiscal ni incluye la base general (trabajo, inmuebles…).
            </p>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => api.exportSavingsEstimate(fiscalYear)}
            >
              Descargar resumen (CSV)
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ManualIncomeCard({
  fiscalYear,
  manual,
  onChanged,
}: {
  fiscalYear: number;
  manual: ManualSavingsIncome[];
  onChanged: () => Promise<void>;
}) {
  const [category, setCategory] =
    useState<Exclude<ManualSavingsIncome["category"], "RCM">>("DIVIDEND");
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [withholding, setWithholding] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    if (!amount || Number(amount) <= 0) return;
    setBusy(true);
    try {
      await api.addManualIncome({
        fiscal_year: fiscalYear,
        category,
        label,
        amount_eur: amount,
        withholding_eur: withholding || "0",
      });
      setLabel("");
      setAmount("");
      setWithholding("");
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await api.deleteManualIncome(id, fiscalYear);
    await onChanged();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ingresos del ahorro fuera de tus brokers</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {manual.length > 0 && (
          <ul className="space-y-2">
            {manual.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between gap-2 text-sm border-b border-border pb-2"
              >
                <span className="flex items-center gap-2">
                  <Badge variant="secondary">{CATEGORY_LABEL[m.category]}</Badge>
                  {m.label && <span className="text-muted-foreground">{m.label}</span>}
                </span>
                <span className="flex items-center gap-3">
                  <span className="tabular-nums">{formatEur(m.amount_eur)}</span>
                  {Number(m.withholding_eur) > 0 && (
                    <span className="text-xs text-muted-foreground">
                      ret. {formatEur(m.withholding_eur)}
                    </span>
                  )}
                  <button
                    onClick={() => remove(m.id)}
                    className="opacity-60 hover:opacity-100"
                    aria-label="Eliminar"
                  >
                    ×
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}

        <div className="flex flex-wrap items-end gap-2">
          <select
            value={category}
            onChange={(e) =>
              setCategory(
                e.target.value as Exclude<ManualSavingsIncome["category"], "RCM">,
              )
            }
            className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
          >
            <option value="INTEREST">Intereses (0027)</option>
            <option value="DIVIDEND">Dividendos (0029)</option>
            <option value="GAIN">Ganancia patrimonial</option>
            <option value="LOSS">Pérdida patrimonial</option>
          </select>
          <Input
            placeholder="Concepto (opcional)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            className="max-w-[180px]"
          />
          <Input
            type="number"
            min={0}
            step="0.01"
            placeholder="Importe €"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="max-w-[120px]"
          />
          <Input
            type="number"
            min={0}
            step="0.01"
            placeholder="Retención €"
            value={withholding}
            onChange={(e) => setWithholding(e.target.value)}
            className="max-w-[120px]"
          />
          <Button onClick={add} disabled={busy} size="sm">
            Añadir
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm">{label}</span>
      {children}
    </div>
  );
}

function Row({
  label,
  value,
  strong,
  muted,
}: {
  label: string;
  value: string;
  strong?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className={muted ? "text-muted-foreground" : ""}>{label}</span>
      <span
        className={`tabular-nums fv-sensitive ${strong ? "font-semibold" : ""}`}
      >
        {formatEur(value)}
      </span>
    </div>
  );
}

function ResultRow({ result }: { result: string }) {
  const n = Number(result);
  const aIngresar = n > 0;
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="font-semibold">
        {aIngresar ? "A ingresar" : "A devolver"}
      </span>
      <span
        className={`text-lg font-bold tabular-nums fv-sensitive ${
          aIngresar ? "text-red-600 dark:text-red-500" : "text-emerald-600 dark:text-emerald-500"
        }`}
      >
        {formatEur(Math.abs(n))}
      </span>
    </div>
  );
}
