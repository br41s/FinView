"use client";

import type { Casilla } from "@/lib/types";
import { formatEur } from "@/lib/format";

export function CasillasTable({ casillas }: { casillas: Casilla[] }) {
  if (casillas.length === 0) return <p className="text-neutral-500 text-sm">Sin datos</p>;

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
              <h3 className="text-sm font-medium text-neutral-400 mb-2">{title}</h3>
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
                    <tr key={`${c.modelo}-${c.casilla}`} className="border-b border-neutral-800/50">
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
