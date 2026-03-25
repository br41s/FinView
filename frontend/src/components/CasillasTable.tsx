"use client";

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

const TAX_BRACKETS = [
  { from: 0, to: 6000, rate: 19 },
  { from: 6000, to: 50000, rate: 21 },
  { from: 50000, to: 200000, rate: 23 },
  { from: 200000, to: 300000, rate: 27 },
  { from: 300000, to: Infinity, rate: 28 },
];

function TaxBracketsSection() {
  return (
    <div>
      <h3 className="text-sm font-medium text-neutral-300 mb-3">
        Tramos de la base del ahorro — IRPF 2024
      </h3>
      <p className="text-xs text-neutral-500 mb-3">
        Los dividendos y ganancias patrimoniales tributan en la base del ahorro del IRPF a los
        siguientes tipos marginales:
      </p>
      <table className="w-full text-sm max-w-md">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-500">
            <th className="text-left py-2">Base liquidable</th>
            <th className="text-right py-2">Tipo</th>
          </tr>
        </thead>
        <tbody>
          {TAX_BRACKETS.map((b) => (
            <tr key={b.from} className="border-b border-neutral-800/50">
              <td className="py-1.5 text-neutral-300">
                {b.to === Infinity
                  ? `Más de ${b.from.toLocaleString("es-ES")} €`
                  : `${b.from.toLocaleString("es-ES")} € — ${b.to.toLocaleString("es-ES")} €`}
              </td>
              <td className="py-1.5 text-right font-mono text-neutral-200">{b.rate}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CountryAnalysis({
  dividendsByCountry,
}: {
  readonly dividendsByCountry: readonly DividendsByCountry[];
}) {
  const foreign = dividendsByCountry.filter(
    (d) => d.country !== "España" && d.country !== "Desconocido"
  );
  if (foreign.length === 0) return null;

  return (
    <div>
      <h3 className="text-sm font-medium text-neutral-300 mb-2">
        Análisis por país — Doble imposición internacional
      </h3>
      <p className="text-xs text-neutral-500 mb-4">
        Deducción aplicable en casilla 588 del Modelo 100 según los Convenios de Doble Imposición
        (CDI) vigentes. El importe deducible es el menor entre: la retención soportada, el bruto ×
        tipo CDI, y la cuota íntegra proporcional española.
      </p>
      <div className="space-y-4">
        {foreign.map((d) => {
          const gross = Number.parseFloat(d.gross);
          const withholding = Number.parseFloat(d.withholding);
          const treatyRate = TREATY_RATES[d.country] ?? 0.15;
          const deductible = Math.min(withholding, gross * treatyRate);
          const excess = Math.max(0, withholding - deductible);
          const note =
            COUNTRY_NOTES[d.country] ?? `Consultar convenio de doble imposición con ${d.country}.`;

          return (
            <div
              key={d.country}
              className="bg-neutral-800/50 border border-neutral-700/50 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-medium text-neutral-200">{d.country}</h4>
                <span className="text-xs text-neutral-500">{d.count} pago(s)</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs mb-3">
                <div>
                  <span className="text-neutral-500">Bruto</span>
                  <p className="text-neutral-200 font-mono">{formatEur(gross)}</p>
                </div>
                <div>
                  <span className="text-neutral-500">Retención origen</span>
                  <p className="text-amber-400 font-mono">{formatEur(withholding)}</p>
                </div>
                <div>
                  <span className="text-neutral-500">Deducible (cas. 588)</span>
                  <p className="text-green-400 font-mono">{formatEur(deductible)}</p>
                </div>
                {excess > 0 && (
                  <div>
                    <span className="text-neutral-500">Exceso reclamable</span>
                    <p className="text-red-400 font-mono">{formatEur(excess)}</p>
                  </div>
                )}
              </div>
              <p className="text-xs text-neutral-400 leading-relaxed">{note}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CasillasSection({ casillas }: { readonly casillas: readonly Casilla[] }) {
  if (casillas.length === 0)
    return <p className="text-neutral-500 text-sm">Sin casillas calculadas</p>;

  const m100 = casillas.filter((c) => c.modelo === 100);
  const m714 = casillas.filter((c) => c.modelo === 714);

  return (
    <div className="space-y-6">
      {[
        { title: "Modelo 100 (IRPF)", items: m100 },
        { title: "Modelo 714 (Patrimonio)", items: m714 },
      ].map(
        ({ title, items }) =>
          items.length > 0 && (
            <div key={title}>
              <h3 className="text-sm font-medium text-neutral-300 mb-2">{title}</h3>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-800 text-neutral-500">
                    <th className="text-left py-2">Casilla</th>
                    <th className="text-left py-2">Descripción</th>
                    <th className="text-right py-2">Importe</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <tr
                      key={`${c.modelo}-${c.casilla}`}
                      className="border-b border-neutral-800/50"
                    >
                      <td className="py-2 font-mono">{c.casilla}</td>
                      <td className="py-2 text-neutral-300">{c.description}</td>
                      <td className="py-2 text-right">{formatEur(c.amount_eur)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
      )}
    </div>
  );
}

function DeclarationGuide() {
  return (
    <div>
      <h3 className="text-sm font-medium text-neutral-300 mb-3">
        Cómo declarar dividendos en el Modelo 100
      </h3>
      <ol className="text-xs text-neutral-400 space-y-2 list-decimal list-inside leading-relaxed">
        <li>
          <strong className="text-neutral-300">Casilla 0029</strong> — Rendimientos íntegros del
          capital mobiliario: total de dividendos brutos recibidos (nacionales y extranjeros).
        </li>
        <li>
          <strong className="text-neutral-300">Casilla 0596</strong> — Retenciones e ingresos a
          cuenta: retenciones practicadas por el broker español (19% sobre dividendos nacionales).
        </li>
        <li>
          <strong className="text-neutral-300">Casilla 0588</strong> — Deducción por doble
          imposición internacional (base del ahorro): importe deducible por retenciones soportadas
          en el extranjero, limitado al menor entre la retención efectiva, el tipo del CDI aplicable
          × bruto, y la cuota íntegra proporcional española.
        </li>
        <li>
          <strong className="text-neutral-300">Exceso de retención</strong> — Si la retención en
          origen supera el límite del CDI (ej. Alemania 26% vs CDI 15%), el exceso debe reclamarse
          directamente a la administración fiscal del país de origen.
        </li>
      </ol>
    </div>
  );
}

export function CasillasTable({
  casillas,
  dividendsByCountry,
}: {
  readonly casillas: readonly Casilla[];
  readonly dividendsByCountry: readonly DividendsByCountry[];
}) {
  return (
    <div className="space-y-8">
      <TaxBracketsSection />
      <CountryAnalysis dividendsByCountry={dividendsByCountry} />
      <CasillasSection casillas={casillas} />
      <DeclarationGuide />
    </div>
  );
}
