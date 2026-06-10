"use client";

import { useMemo, useState } from "react";
import type { Casilla, DividendsByCountry } from "@/lib/types";
import { formatEur } from "@/lib/format";

const TREATY_RATES: Record<string, number> = {
  "Estados Unidos de América": 0.15,
  Alemania: 0.15,
  Francia: 0.15,
  Suiza: 0.15,
  "Reino Unido": 0,
  Brasil: 0,
  Portugal: 0.15,
  "Países Bajos": 0.15,
  Italia: 0.15,
  Irlanda: 0,
  Bélgica: 0.15,
  Austria: 0.15,
  Noruega: 0.15,
  Suecia: 0.15,
  Finlandia: 0.15,
  Dinamarca: 0.15,
  Canadá: 0.15,
  Japón: 0.1,
  Australia: 0.15,
};

const COUNTRY_NOTES: Record<string, string> = {
  "Estados Unidos de América":
    "Convenio España-EEUU. Retención en origen 15% (con W-8BEN). Deducible al 100% por doble imposición internacional en casilla 588 del Modelo 100.",
  Alemania:
    "Convenio España-Alemania. Retención en origen ~26,375% (Kapitalertragsteuer). Deducible hasta 15% (CDI) en casilla 588. El exceso (11,375%) es reclamable ante el Bundeszentralamt für Steuern.",
  Francia:
    "Convenio España-Francia. Retención en origen 25% (puede reducirse a 12,8% con formulario adecuado). Deducible hasta 15% (CDI) en casilla 588. Exceso reclamable ante la administración fiscal francesa.",
  Suiza:
    "Convenio España-Suiza. Retención en origen 35% (Verrechnungssteuer). Deducible hasta 15% (CDI) en casilla 588. Exceso reclamable mediante formulario 6300 de la administración suiza.",
  "Reino Unido":
    "Convenio España-Reino Unido. Sin retención en origen sobre dividendos. No aplica deducción por doble imposición.",
  Brasil:
    "Convenio España-Brasil. Dividendos exentos de retención en origen. No aplica deducción por doble imposición.",
  Portugal:
    "Convenio España-Portugal. Retención en origen 28%. Deducible hasta 15% (CDI) en casilla 588. Exceso reclamable ante la administración fiscal portuguesa.",
  "Países Bajos":
    "Convenio España-Países Bajos. Retención en origen 15%. Deducible al 100% en casilla 588.",
  Italia:
    "Convenio España-Italia. Retención en origen 26%. Deducible hasta 15% (CDI) en casilla 588. Exceso reclamable ante la Agenzia delle Entrate.",
  Irlanda:
    "Convenio España-Irlanda. Sin retención en origen sobre dividendos para no residentes.",
};

function CountryAnalysis({
  dividendsByCountry,
}: {
  readonly dividendsByCountry: readonly DividendsByCountry[];
}) {
  const foreign = dividendsByCountry.filter(
    (d) => d.country !== "España" && d.country !== "Desconocido",
  );
  if (foreign.length === 0) return null;

  return (
    <div>
      <h3 className="text-sm font-medium text-foreground mb-2">
        Análisis por país — Doble imposición internacional
      </h3>
      <p className="text-xs text-muted-foreground mb-4">
        Deducción aplicable en casilla 588 del Modelo 100 según los Convenios de
        Doble Imposición (CDI) vigentes. El importe deducible es el menor entre:
        la retención soportada, el bruto × tipo CDI, y la cuota íntegra
        proporcional española.
      </p>
      <div className="space-y-4">
        {foreign.map((d) => {
          const gross = Number.parseFloat(d.gross);
          const withholding = Number.parseFloat(d.withholding);
          const treatyRate = TREATY_RATES[d.country] ?? 0.15;
          const deductible = Math.min(withholding, gross * treatyRate);
          const excess = Math.max(0, withholding - deductible);
          const note =
            COUNTRY_NOTES[d.country] ??
            `Consultar convenio de doble imposición con ${d.country}.`;

          return (
            <div
              key={d.country}
              className="bg-muted/50 border border-border/50 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-medium text-foreground">
                  {d.country}
                </h4>
                <span className="text-xs text-muted-foreground">
                  {d.count} pago(s)
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                <div>
                  <span className="text-muted-foreground">Bruto</span>
                  <p className="text-foreground font-mono">
                    {formatEur(gross)}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">
                    Retención origen
                  </span>
                  <p className="text-amber-400 font-mono">
                    {formatEur(withholding)}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">
                    Deducible (cas. 588)
                  </span>
                  <p className="text-green-400 font-mono">
                    {formatEur(deductible)}
                  </p>
                </div>
                {excess > 0 && (
                  <div>
                    <span className="text-muted-foreground">
                      Exceso reclamable
                    </span>
                    <p className="text-red-400 font-mono">
                      {formatEur(excess)}
                    </p>
                  </div>
                )}
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {note}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function brokerAmount(c: Casilla, broker: string): string | undefined {
  return c.brokers?.find((b) => b.broker === broker)?.amount_eur;
}

function CasillasSection({
  casillas,
  selectedBroker,
}: {
  readonly casillas: readonly Casilla[];
  readonly selectedBroker: string | null;
}) {
  if (casillas.length === 0)
    return (
      <p className="text-muted-foreground text-sm">Sin casillas calculadas</p>
    );

  // When a broker is selected, keep only casillas that broker reports.
  const visible = (list: readonly Casilla[]) =>
    selectedBroker
      ? list.filter((c) => brokerAmount(c, selectedBroker) !== undefined)
      : list;

  const m100 = visible(casillas.filter((c) => c.modelo === 100));
  const m714 = visible(casillas.filter((c) => c.modelo === 714));

  if (m100.length === 0 && m714.length === 0)
    return (
      <p className="text-muted-foreground text-sm">
        Sin casillas para {selectedBroker} en este año.
      </p>
    );

  return (
    <div className="space-y-6">
      {[
        { title: "Modelo 100 (IRPF)", items: m100 },
        { title: "Modelo 714 (Patrimonio)", items: m714 },
      ].map(
        ({ title, items }) =>
          items.length > 0 && (
            <div key={title}>
              <h3 className="text-sm font-medium text-foreground mb-2">
                {title}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="text-left py-2">Casilla</th>
                      <th className="text-left py-2">Descripción</th>
                      <th className="text-right py-2">Importe</th>
                      <th className="text-center py-2 w-10">TR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((c) => {
                      // When filtering by broker, show that broker's own
                      // contribution and hide cross-broker context (multi-broker
                      // breakdown, FIFO adjustment). The TR validation badge only
                      // applies to the aggregate or the TR-filtered view.
                      const amount = selectedBroker
                        ? (brokerAmount(c, selectedBroker) ?? c.amount_eur)
                        : c.amount_eur;
                      const showCrossBroker = !selectedBroker;
                      const showBadge = !selectedBroker || selectedBroker === "TR";
                      return (
                      <tr
                        key={`${c.modelo}-${c.casilla}`}
                        className="border-b border-border/50"
                      >
                        <td className="py-2 font-mono">{c.casilla}</td>
                        <td className="py-2 text-foreground">
                          {c.description}
                          {showCrossBroker && c.brokers && c.brokers.length > 1 && (
                            <span className="block text-xs text-muted-foreground mt-0.5">
                              {c.brokers
                                .map(
                                  (b) =>
                                    `${b.broker}: ${formatEur(b.amount_eur)}`,
                                )
                                .join(" · ")}
                            </span>
                          )}
                          {showCrossBroker &&
                            c.fifo_adjustment_eur &&
                            Number(c.fifo_adjustment_eur) !== 0 && (
                              <span className="block text-xs text-amber-400 mt-1">
                                ⚠ Ajuste FIFO cruzado:{" "}
                                {Number(c.fifo_adjustment_eur) > 0 ? "+" : ""}
                                {formatEur(c.fifo_adjustment_eur)} (diferencia
                                entre FIFO global y broker)
                              </span>
                            )}
                        </td>
                        <td className="py-2 text-right font-mono">
                          {formatEur(amount)}
                          {showCrossBroker &&
                            c.fifo_adjustment_eur &&
                            Number(c.fifo_adjustment_eur) !== 0 && (
                              <span className="block text-xs text-amber-400 mt-1 font-mono">
                                ⚠ Ajustado:{" "}
                                {formatEur(
                                  Number(c.amount_eur) +
                                    Number(c.fifo_adjustment_eur),
                                )}
                              </span>
                            )}
                        </td>
                        <td className="py-2 text-center">
                          {showBadge && c.validation_status === "match" && (
                            <span
                              title={`TR ref: ${formatEur(c.tr_reference_amount ?? 0)}`}
                              className="text-green-400 cursor-help"
                            >
                              ✅
                            </span>
                          )}
                          {showBadge && c.validation_status === "mismatch" && (
                            <span
                              title={`TR ref: ${formatEur(c.tr_reference_amount ?? 0)} — Δ ${formatEur(Math.abs(Number(c.amount_eur) - Number(c.tr_reference_amount ?? 0)))}`}
                              className="text-amber-400 cursor-help"
                            >
                              ⚠️
                            </span>
                          )}
                        </td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ),
      )}
    </div>
  );
}

function DeclarationGuide() {
  return (
    <div>
      <h3 className="text-sm font-medium text-foreground mb-3">
        Cómo declarar dividendos en el Modelo 100
      </h3>
      <ol className="text-xs text-muted-foreground space-y-2 list-decimal list-inside leading-relaxed">
        <li>
          <strong className="text-foreground">Casilla 0029</strong> —
          Rendimientos íntegros del capital mobiliario: total de dividendos
          brutos recibidos (nacionales y extranjeros).
        </li>
        <li>
          <strong className="text-foreground">Casilla 0596</strong> —
          Retenciones e ingresos a cuenta: retenciones practicadas por el broker
          español (19% sobre dividendos nacionales).
        </li>
        <li>
          <strong className="text-foreground">Casilla 0588</strong> — Deducción
          por doble imposición internacional (base del ahorro): importe
          deducible por retenciones soportadas en el extranjero, limitado al
          menor entre la retención efectiva, el tipo del CDI aplicable × bruto,
          y la cuota íntegra proporcional española.
        </li>
        <li>
          <strong className="text-foreground">Exceso de retención</strong> — Si
          la retención en origen supera el límite del CDI (ej. Alemania 26% vs
          CDI 15%), el exceso debe reclamarse directamente a la administración
          fiscal del país de origen.
        </li>
      </ol>
    </div>
  );
}

export function CasillasTable({
  casillas,
  dividendsByCountry,
  fiscalYear,
}: {
  readonly casillas: readonly Casilla[];
  readonly dividendsByCountry: readonly DividendsByCountry[];
  readonly fiscalYear?: number | null;
}) {
  const [selectedBroker, setSelectedBroker] = useState<string | null>(null);

  // Brokers present in this year's casillas — source for the review filter.
  const availableBrokers = useMemo(() => {
    const set = new Set<string>();
    for (const c of casillas) for (const b of c.brokers ?? []) set.add(b.broker);
    return Array.from(set).sort();
  }, [casillas]);

  const handleExport = async (format: "json" | "csv") => {
    if (!fiscalYear) return;
    try {
      const { api } = await import("@/lib/api");
      if (format === "csv") {
        await api.exportFiscal(fiscalYear, "csv");
      } else {
        const data = await api.exportFiscal(fiscalYear, "json");
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `finview_casillas_${fiscalYear}.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error("Export failed:", err);
    }
  };

  return (
    <div className="space-y-8">
      <CountryAnalysis dividendsByCountry={dividendsByCountry} />
      {availableBrokers.length > 1 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">
            Revisar por broker:
          </span>
          <button
            onClick={() => setSelectedBroker(null)}
            className={`px-3 py-1 text-xs rounded-lg border transition-colors ${
              selectedBroker === null
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-muted hover:bg-muted/80 border-border"
            }`}
          >
            Todos
          </button>
          {availableBrokers.map((b) => (
            <button
              key={b}
              onClick={() => setSelectedBroker(b)}
              className={`px-3 py-1 text-xs rounded-lg border transition-colors ${
                selectedBroker === b
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted hover:bg-muted/80 border-border"
              }`}
            >
              {b}
            </button>
          ))}
        </div>
      )}
      {selectedBroker && (
        <p className="-mt-4 text-xs text-muted-foreground">
          Mostrando solo la aportación de <strong>{selectedBroker}</strong> a
          cada casilla — compara estos importes con el informe fiscal de {selectedBroker}.
        </p>
      )}
      <CasillasSection casillas={casillas} selectedBroker={selectedBroker} />
      {fiscalYear && (
        <div className="flex gap-2">
          <button
            onClick={() => handleExport("json")}
            className="px-3 py-1.5 text-xs bg-muted hover:bg-muted/80 border border-border rounded-lg transition-colors"
          >
            Exportar JSON
          </button>
          <button
            onClick={() => handleExport("csv")}
            className="px-3 py-1.5 text-xs bg-muted hover:bg-muted/80 border border-border rounded-lg transition-colors"
          >
            Exportar CSV
          </button>
        </div>
      )}
      <DeclarationGuide />
    </div>
  );
}
