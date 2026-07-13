"use client";

import { useState } from "react";
import type {
  CapitalGain,
  CrossBrokerLot,
  FIFOAdjustment,
  OptionAssignment,
} from "@/lib/types";
import { formatEur, plColor } from "@/lib/format";

function CrossBrokerSection({
  lots,
  adjustments,
}: {
  readonly lots: CrossBrokerLot[];
  readonly adjustments: FIFOAdjustment[];
}) {
  const [open, setOpen] = useState(false);

  if (lots.length === 0 && adjustments.length === 0) return null;

  return (
    <div className="mt-6 border border-amber-700/40 rounded-lg bg-amber-950/20">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 flex items-center justify-between text-sm font-medium text-amber-300 hover:bg-amber-950/30 rounded-lg"
      >
        <span>
          ⚠ FIFO Cruzado — {lots.length} lotes, {adjustments.length} ajuste(s)
        </span>
        <span className="text-xs">{open ? "▼" : "▶"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4">
          {adjustments.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-medium text-amber-400">
                Resumen de ajustes
              </h4>
              {adjustments.map((a) => (
                <div
                  key={a.id}
                  className="bg-muted/50 border border-border/50 rounded p-3 text-xs"
                >
                  <div className="flex justify-between mb-1">
                    <span className="text-foreground font-medium">
                      {a.name}
                    </span>
                    <span className="font-mono text-muted-foreground">
                      {a.isin}
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-muted-foreground">
                    <div>
                      Broker:{" "}
                      <span className="font-mono text-foreground">
                        {formatEur(a.broker_pl_eur)}
                      </span>
                    </div>
                    <div>
                      FIFO global:{" "}
                      <span className="font-mono text-foreground">
                        {formatEur(a.fifo_pl_eur)}
                      </span>
                    </div>
                    <div>
                      Ajuste:{" "}
                      <span
                        className={`font-mono font-medium ${plColor(a.adjustment_eur)}`}
                      >
                        {Number(a.adjustment_eur) > 0 ? "+" : ""}
                        {formatEur(a.adjustment_eur)}
                      </span>
                    </div>
                  </div>
                  <p className="mt-1 text-muted-foreground">{a.note}</p>
                </div>
              ))}
            </div>
          )}

          {lots.length > 0 && (
            <div>
              <h4 className="text-xs font-medium text-amber-400 mb-2">
                Lotes FIFO cruzado
              </h4>
              {/* Mobile */}
              <div className="divide-y divide-border/30 sm:hidden">
                {lots.map((l) => (
                  <div key={l.id} className="py-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-muted-foreground">{l.isin}</span>
                      <span className={`font-medium ${plColor(l.realized_pl_eur)}`}>
                        {formatEur(l.realized_pl_eur)}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-muted-foreground">
                      <span>
                        {l.buy_broker} → {l.sell_broker}
                      </span>
                      <span>{l.quantity} uds</span>
                      <span>Coste {formatEur(l.cost_basis_eur)}</span>
                      <span>Venta {formatEur(l.proceeds_eur)}</span>
                      <span>{l.holding_period ?? "—"}</span>
                      <span>Casilla {l.casilla}</span>
                    </div>
                  </div>
                ))}
              </div>
              {/* Desktop */}
              <div className="hidden overflow-x-auto sm:block">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground">
                      <th className="text-left py-1.5">ISIN</th>
                      <th className="text-left py-1.5">Compra en</th>
                      <th className="text-left py-1.5">Venta en</th>
                      <th className="text-right py-1.5">Cantidad</th>
                      <th className="text-right py-1.5">Coste</th>
                      <th className="text-right py-1.5">Venta</th>
                      <th className="text-right py-1.5">P&L</th>
                      <th className="text-left py-1.5">Periodo</th>
                      <th className="text-right py-1.5">Casilla</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lots.map((l) => (
                      <tr key={l.id} className="border-b border-border/30">
                        <td className="py-1.5 font-mono text-muted-foreground">
                          {l.isin}
                        </td>
                        <td className="py-1.5 text-foreground">
                          {l.buy_broker}
                        </td>
                        <td className="py-1.5 text-foreground">
                          {l.sell_broker}
                        </td>
                        <td className="py-1.5 text-right text-foreground">
                          {l.quantity}
                        </td>
                        <td className="py-1.5 text-right">
                          {formatEur(l.cost_basis_eur)}
                        </td>
                        <td className="py-1.5 text-right">
                          {formatEur(l.proceeds_eur)}
                        </td>
                        <td
                          className={`py-1.5 text-right font-medium ${plColor(l.realized_pl_eur)}`}
                        >
                          {formatEur(l.realized_pl_eur)}
                        </td>
                        <td className="py-1.5 text-muted-foreground">
                          {l.holding_period ?? "—"}
                        </td>
                        <td className="py-1.5 text-right font-mono">
                          {l.casilla}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AssignmentsSection({
  assignments,
}: {
  readonly assignments: OptionAssignment[];
}) {
  const [open, setOpen] = useState(false);
  if (assignments.length === 0) return null;

  return (
    <div className="mt-6 border border-blue-700/40 rounded-lg bg-blue-950/20">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-4 py-3 flex items-center justify-between text-sm font-medium text-blue-300 hover:bg-blue-950/30 rounded-lg"
      >
        <span>
          ℹ Asignaciones de opciones — {assignments.length} detectada(s)
        </span>
        <span className="text-xs">{open ? "▼" : "▶"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-2">
          <p className="text-xs text-blue-400/80 mb-3">
            Las primas de opciones asignadas están integradas en el coste de
            adquisición de las acciones por IBKR. No generan ganancia/pérdida
            independiente (art. 37.1.n LIRPF).
          </p>
          {assignments.map((a) => (
            <div
              key={a.id}
              className="bg-muted/50 border border-border/50 rounded p-3 text-xs"
            >
              <div className="flex justify-between mb-1">
                <span className="text-foreground font-medium">
                  {a.option_type} {a.option_symbol}
                </span>
                <span className="text-muted-foreground">
                  {a.assignment_date}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-muted-foreground">
                <div>
                  Acción:{" "}
                  <span className="text-foreground">{a.underlying}</span>
                  {a.stock_isin && (
                    <span className="font-mono ml-1">({a.stock_isin})</span>
                  )}
                </div>
                <div>
                  {a.stock_quantity} acc. @ ${a.strike}
                </div>
                <div>
                  Prima:{" "}
                  <span className="font-mono text-blue-300">
                    {formatEur(a.premium_eur)}
                  </span>
                  {" → coste base"}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function CapitalGainsTable({
  gains,
  crossBrokerLots = [],
  fifoAdjustments = [],
  optionAssignments = [],
}: Readonly<{
  gains: CapitalGain[];
  crossBrokerLots?: CrossBrokerLot[];
  fifoAdjustments?: FIFOAdjustment[];
  optionAssignments?: OptionAssignment[];
}>) {
  if (gains.length === 0)
    return <p className="text-muted-foreground text-sm">Sin datos</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-muted-foreground">
            <th className="text-left py-2">Empresa</th>
            <th className="text-left py-2 hidden lg:table-cell">ISIN</th>
            <th className="text-left py-2 hidden sm:table-cell">Compra</th>
            <th className="text-left py-2">Venta</th>
            <th className="text-right py-2 hidden md:table-cell">Cantidad</th>
            <th className="text-right py-2 hidden sm:table-cell">Coste</th>
            <th className="text-right py-2 hidden sm:table-cell">Venta</th>
            <th className="text-right py-2">P&L</th>
            <th className="text-left py-2 hidden md:table-cell">Periodo</th>
          </tr>
        </thead>
        <tbody>
          {gains.map((g) => (
            <tr
              key={g.id}
              className="border-b border-border/50 hover:bg-muted/30"
            >
              <td className="py-2 text-foreground">{g.name}</td>
              <td className="py-2 font-mono text-xs text-muted-foreground hidden lg:table-cell">
                {g.isin}
              </td>
              <td className="py-2 text-foreground hidden sm:table-cell">
                {g.buy_date}
              </td>
              <td className="py-2 text-foreground">{g.sell_date}</td>
              <td className="py-2 text-right text-foreground hidden md:table-cell">
                {g.quantity}
              </td>
              <td className="py-2 text-right hidden sm:table-cell">
                {formatEur(g.cost_basis_eur)}
              </td>
              <td className="py-2 text-right hidden sm:table-cell">
                {formatEur(g.proceeds_eur)}
              </td>
              <td
                className={`py-2 text-right font-medium ${plColor(g.realized_pl_eur)}`}
              >
                {formatEur(g.realized_pl_eur)}
              </td>
              <td className="py-2 text-muted-foreground text-xs hidden md:table-cell">
                {g.holding_period ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <CrossBrokerSection
        lots={crossBrokerLots}
        adjustments={fifoAdjustments}
      />
      <AssignmentsSection assignments={optionAssignments} />
    </div>
  );
}
