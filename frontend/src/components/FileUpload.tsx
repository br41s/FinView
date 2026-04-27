"use client";

import { useState, useCallback, useRef, useMemo } from "react";
import { toast } from "sonner";
import {
  uploadTRReport,
  uploadDGReport,
  uploadIBKRReport,
  uploadINGReport,
  uploadBBVAReport,
  uploadEToroReport,
  resolveIssue,
} from "@/lib/api";
import type { ImportResult, DataIssue } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Upload,
  FileUp,
  Loader2,
  CheckCircle2,
  AlertTriangle,
  Info,
} from "lucide-react";

type BrokerKey = "tr" | "degiro" | "ibkr" | "ing" | "bbva" | "etoro";
type UploadMapKey = "tr" | "degiro" | "ibkr" | "ing" | "etoro";

type BrokerConfig = {
  readonly key: BrokerKey;
  readonly label: string;
  readonly shortLabel: string;
  readonly accept: string;
  readonly color: string;
  readonly multi: boolean;
};

const BROKERS: BrokerConfig[] = [
  {
    key: "tr",
    label: "Trade Republic",
    shortLabel: "TR",
    accept: ".pdf,.csv",
    color: "bg-neutral-800 hover:bg-neutral-700 border-neutral-600",
    multi: false,
  },
  {
    key: "degiro",
    label: "DEGIRO",
    shortLabel: "DEGIRO",
    accept: ".pdf",
    color: "bg-orange-950/50 hover:bg-orange-900/50 border-orange-700/40",
    multi: false,
  },
  {
    key: "ibkr",
    label: "IBKR",
    shortLabel: "IBKR",
    accept: ".csv",
    color: "bg-red-950/50 hover:bg-red-900/50 border-red-700/40",
    multi: false,
  },
  {
    key: "ing",
    label: "ING",
    shortLabel: "ING",
    accept: ".pdf",
    color: "bg-orange-950/40 hover:bg-orange-900/40 border-orange-600/30",
    multi: false,
  },
  {
    key: "bbva",
    label: "BBVA",
    shortLabel: "BBVA",
    accept: ".pdf",
    color: "bg-blue-950/50 hover:bg-blue-900/50 border-blue-700/40",
    multi: true,
  },
  {
    key: "etoro",
    label: "eToro",
    shortLabel: "eToro",
    accept: ".xlsx",
    color: "bg-green-950/50 hover:bg-green-900/50 border-green-700/40",
    multi: false,
  },
];

interface FileUploadProps {
  readonly onImported: () => void;
}

function detectBroker(
  filename: string,
): "tr" | "degiro" | "ibkr" | "ing" | "bbva" | "etoro" | null {
  const lower = filename.toLowerCase();
  if (
    lower.startsWith("dg-") ||
    lower.includes("degiro") ||
    lower.includes("informe anual")
  )
    return "degiro";
  if (
    lower.startsWith("tr-") ||
    lower.includes("trade republic") ||
    lower.includes("tax_report") ||
    lower.includes("transaction export")
  )
    return "tr";
  if (
    lower.startsWith("ibkr") ||
    lower.includes("interactive") ||
    lower.includes("u1104")
  )
    return "ibkr";
  if (
    lower.includes("ing") ||
    lower.includes("información fiscal") ||
    lower.includes("informacion fiscal")
  )
    return "ing";
  if (lower.includes("bbva")) return "bbva";
  if (lower.includes("etoro") || lower.includes("account-statement"))
    return "etoro";
  return null;
}

// ---------------------------------------------------------------------------
// IssueCard — interactive card for a single DataIssue
// ---------------------------------------------------------------------------

const ACTIONABLE_TYPES = new Set([
  "zero_price",
  "missing_buy",
  "potential_split",
  "holdings_mismatch",
]);

function IssueCard({
  issue,
  onResolved,
}: Readonly<{
  issue: DataIssue;
  onResolved: (id: number, updated: DataIssue) => void;
}>) {
  const [submitting, setSubmitting] = useState(false);
  const [price, setPrice] = useState("");
  const [qty, setQty] = useState("");
  const [buyPrice, setBuyPrice] = useState("");
  const [buyDate, setBuyDate] = useState("");

  const resData = useMemo(() => {
    try {
      return issue.resolution_data ? JSON.parse(issue.resolution_data) : null;
    } catch {
      return null;
    }
  }, [issue.resolution_data]);

  const isSettled =
    issue.status === "auto_resolved" ||
    issue.status === "resolved" ||
    issue.status === "dismissed";
  const needsInput = issue.status === "needs_input" && ACTIONABLE_TYPES.has(issue.issue_type);

  let colorClass = "bg-blue-500/10 border border-blue-500/20 text-blue-300";
  let IssueIcon = Info;
  if (isSettled) {
    colorClass = "bg-green-500/10 border border-green-500/20 text-green-300";
    IssueIcon = CheckCircle2;
  } else if (issue.severity === "warning" || needsInput) {
    colorClass =
      "bg-yellow-500/10 border border-yellow-500/20 text-yellow-300";
    IssueIcon = AlertTriangle;
  }

  async function handleAction(
    action: string,
    data?: Record<string, unknown>,
  ) {
    setSubmitting(true);
    try {
      const updated = (await resolveIssue(issue.id, action, data)) as DataIssue;
      onResolved(issue.id, updated);
      toast.success(
        action === "dismiss" ? "Aviso ignorado" : "Corrección aplicada",
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Error desconocido";
      toast.error("Error al aplicar corrección", { description: msg });
    } finally {
      setSubmitting(false);
    }
  }

  const inputCls =
    "text-xs bg-background border border-input rounded px-2 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-ring";
  const applyBtnCls =
    "text-xs bg-yellow-600/20 hover:bg-yellow-600/30 border border-yellow-600/40 rounded px-2 py-1 disabled:opacity-50 transition-colors";
  const dismissBtnCls =
    "text-xs text-muted-foreground hover:text-foreground px-2 py-1 transition-colors";

  return (
    <div className={`text-xs px-3 py-2 rounded ${colorClass}`}>
      <span className="font-medium flex items-center gap-1 flex-wrap">
        <IssueIcon className="h-3 w-3 shrink-0" />
        {issue.issue_type.replaceAll("_", " ")}
        {issue.isin && (
          <span className="text-muted-foreground">({issue.isin})</span>
        )}
        {issue.status === "dismissed" && (
          <span className="text-muted-foreground italic ml-1">(ignorado)</span>
        )}
        {issue.status === "resolved" && (
          <span className="text-green-400 italic ml-1">(resuelto)</span>
        )}
      </span>
      <p className="mt-0.5 text-muted-foreground">{issue.description}</p>
      {issue.auto_resolution && (
        <p className="mt-0.5 italic text-green-400/70">
          {issue.auto_resolution}
        </p>
      )}

      {/* zero_price: ask for the correct purchase price */}
      {needsInput && issue.issue_type === "zero_price" && (
        <div className="mt-2 flex gap-2 items-center flex-wrap">
          <input
            type="number"
            step="0.0001"
            min="0.0001"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="Precio €/acción"
            className={`${inputCls} w-32`}
          />
          <button
            type="button"
            disabled={submitting || !price || Number.parseFloat(price) <= 0}
            onClick={() =>
              handleAction("set_price", {
                price: Number.parseFloat(price),
              })
            }
            className={applyBtnCls}
          >
            {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : "Aplicar precio"}
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={() => handleAction("dismiss")}
            className={dismissBtnCls}
          >
            Ignorar
          </button>
        </div>
      )}

      {/* missing_buy: register a manual buy (e.g. inherited stocks) */}
      {needsInput && issue.issue_type === "missing_buy" && (
        <div className="mt-2 space-y-2">
          <div className="flex gap-2 flex-wrap items-center">
            <input
              type="number"
              step="0.000001"
              min="0.000001"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder="Acciones"
              className={`${inputCls} w-24`}
            />
            <input
              type="number"
              step="0.0001"
              min="0.0001"
              value={buyPrice}
              onChange={(e) => setBuyPrice(e.target.value)}
              placeholder="Precio €/acción"
              className={`${inputCls} w-32`}
            />
            <input
              type="date"
              aria-label="Fecha de adquisición"
              value={buyDate}
              onChange={(e) => setBuyDate(e.target.value)}
              className={`${inputCls}`}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={
                submitting ||
                !qty ||
                !buyPrice ||
                !buyDate ||
                Number.parseFloat(qty) <= 0 ||
                Number.parseFloat(buyPrice) <= 0
              }
              onClick={() =>
                handleAction("add_buy", {
                  qty: Number.parseFloat(qty),
                  price: Number.parseFloat(buyPrice),
                  acquisition_date: buyDate,
                })
              }
              className={applyBtnCls}
            >
              {submitting ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                "Registrar compra"
              )}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleAction("dismiss")}
              className={dismissBtnCls}
            >
              Ignorar
            </button>
          </div>
        </div>
      )}

      {/* potential_split: show details from resolution_data + confirm button */}
      {needsInput && issue.issue_type === "potential_split" && resData && (
        <div className="mt-2 space-y-1.5">
          <p className="text-muted-foreground">
            Ratio{" "}
            <span className="text-foreground font-medium">{resData.ratio}x</span>{" "}
            · {resData.ticker} · {resData.split_date}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleAction("apply_split")}
              className={applyBtnCls}
            >
              {submitting ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                "Aplicar split"
              )}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleAction("dismiss")}
              className={dismissBtnCls}
            >
              Ignorar
            </button>
          </div>
        </div>
      )}

      {/* holdings_mismatch: register the gap qty as a manual buy */}
      {needsInput && issue.issue_type === "holdings_mismatch" && resData && (
        <div className="mt-2 space-y-2">
          <p className="text-muted-foreground">
            Diferencia:{" "}
            <span className="text-foreground font-medium">
              {resData.difference}
            </span>{" "}
            acciones (esperadas {resData.expected_qty}, calculadas{" "}
            {resData.calculated_qty})
          </p>
          <div className="flex gap-2 flex-wrap items-center">
            <input
              type="number"
              step="0.0001"
              min="0.0001"
              value={buyPrice}
              onChange={(e) => setBuyPrice(e.target.value)}
              placeholder="Precio €/acción adquisición"
              className={`${inputCls} w-44`}
            />
            <input
              type="date"
              aria-label="Fecha de adquisición"
              value={buyDate}
              onChange={(e) => setBuyDate(e.target.value)}
              className={`${inputCls}`}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={
                submitting ||
                !buyPrice ||
                !buyDate ||
                Number.parseFloat(buyPrice) <= 0
              }
              onClick={() =>
                handleAction("add_buy", {
                  qty: Number.parseFloat(resData.difference),
                  price: Number.parseFloat(buyPrice),
                  acquisition_date: buyDate,
                })
              }
              className={applyBtnCls}
            >
              {submitting ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                "Registrar diferencia"
              )}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleAction("dismiss")}
              className={dismissBtnCls}
            >
              Ignorar
            </button>
          </div>
        </div>
      )}

      {/* needs_input but no interactive form: just a dismiss button */}
      {issue.status === "needs_input" &&
        !ACTIONABLE_TYPES.has(issue.issue_type) && (
          <div className="mt-2">
            <button
              type="button"
              disabled={submitting}
              onClick={() => handleAction("dismiss")}
              className={`${dismissBtnCls} border border-muted rounded`}
            >
              Ignorar
            </button>
          </div>
        )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FileUpload
// ---------------------------------------------------------------------------

export function FileUpload({ onImported }: FileUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingBroker, setLoadingBroker] = useState(null as string | null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [resolvedIssues, setResolvedIssues] = useState<Map<number, DataIssue>>(
    new Map(),
  );
  const [error, setError] = useState<string | null>(null);
  const brokerInputRefs = useRef({} as Record<string, HTMLInputElement | null>);

  function handleResolved(id: number, updated: DataIssue) {
    setResolvedIssues((prev) => new Map(prev).set(id, updated));
  }

  const notifyResult = useCallback(
    (res: ImportResult) => {
      if (res.status === "success" || res.status === "replaced") {
        toast.success(
          `${res.status === "replaced" ? "Reemplazado" : "Importado"} — Año fiscal ${res.fiscal_year}`,
          {
            description: res.counts
              ? `${res.counts.dividends} dividendos, ${res.counts.transactions} transacciones`
              : undefined,
          },
        );
        onImported();
      } else if (res.status === "duplicate") {
        toast.warning("Importación duplicada", { description: res.message });
      }
    },
    [onImported],
  );

  const uploadBroker = useCallback(async (file: File, broker: string) => {
    const uploadMap = {
      degiro: uploadDGReport,
      tr: uploadTRReport,
      ibkr: uploadIBKRReport,
      ing: uploadINGReport,
      etoro: uploadEToroReport,
    };
    const upload = uploadMap[broker as UploadMapKey];
    return upload(file);
  }, []);

  const handleFiles = useCallback(
    async (files: File[]) => {
      const invalidFile = files.find((f) => {
        const ext = f.name.toLowerCase();
        return (
          !ext.endsWith(".pdf") &&
          !ext.endsWith(".csv") &&
          !ext.endsWith(".xlsx")
        );
      });
      if (invalidFile) {
        setError("Solo se aceptan archivos PDF, CSV o XLSX");
        return;
      }

      const brokers = files.map((f) => detectBroker(f.name));
      const hasBBVA = brokers.includes("bbva");

      setLoading(true);
      setLoadingBroker(null);
      setError(null);
      setResult(null);
      setResolvedIssues(new Map());

      try {
        let res: ImportResult;
        if (hasBBVA) {
          const bbvaFiles = files.filter(
            (f) => detectBroker(f.name) === "bbva",
          );
          if (bbvaFiles.length === 0 || bbvaFiles.length > 3) {
            setError("BBVA: selecciona entre 1 y 3 archivos PDF del mismo año");
            return;
          }
          res = await uploadBBVAReport(bbvaFiles);
        } else {
          const file = files[0];
          const broker = detectBroker(file.name);
          if (!broker) {
            setError(
              "No se pudo detectar el broker. El archivo debe contener 'TR-', 'DG-', 'IBKR', 'ING', 'BBVA' o 'eToro'.",
            );
            return;
          }
          res = await uploadBroker(file, broker);
        }
        setResult(res);
        notifyResult(res);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Error desconocido";
        setError(msg);
        toast.error("Error de importación", { description: msg });
      } finally {
        setLoading(false);
      }
    },
    [onImported, notifyResult, uploadBroker],
  );

  return (
    <Card
      className={`border-2 border-dashed transition-colors ${
        dragging
          ? "border-primary bg-primary/5"
          : "border-border hover:border-muted-foreground/50"
      }`}
    >
      <CardContent
        className="p-8 text-center"
        role="region"
        aria-label="Zona de carga de archivos"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const files = Array.from(e.dataTransfer.files);
          if (files.length > 0) handleFiles(files);
        }}
      >
        <div className="mb-3">
          <Upload className="h-10 w-10 mx-auto text-muted-foreground" />
        </div>
        <p className="text-muted-foreground mb-4 text-sm">
          Arrastra aquí archivos de Trade Republic (PDF o CSV), DEGIRO (PDF),
          IBKR (CSV), ING (PDF), BBVA (1-3 PDFs) o eToro (XLSX)
        </p>
        <input
          type="file"
          accept=".pdf,.csv,.xlsx"
          multiple
          id="file-upload"
          aria-label="Seleccionar archivos"
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) handleFiles(files);
          }}
        />
        <Button
          variant="default"
          onClick={() => document.getElementById("file-upload")?.click()}
          disabled={loading}
        >
          {loading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Procesando...
            </>
          ) : (
            <>
              <FileUp className="mr-2 h-4 w-4" />
              Seleccionar archivos
            </>
          )}
        </Button>

        {/* Broker-specific buttons */}
        <div className="mt-6 border-t border-border pt-5">
          <p className="text-xs text-muted-foreground mb-3">
            O selecciona directamente por broker:
          </p>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {BROKERS.map((b) => (
              <div key={b.key}>
                <input
                  type="file"
                  accept={b.accept}
                  multiple={b.multi}
                  className="hidden"
                  aria-label={`Importar archivo de ${b.label}`}
                  ref={(el) => {
                    brokerInputRefs.current[b.key] = el;
                  }}
                  onChange={async (e) => {
                    const files = Array.from(e.target.files ?? []);
                    if (files.length === 0) return;
                    setLoading(true);
                    setLoadingBroker(b.key);
                    setError(null);
                    setResult(null);
                    setResolvedIssues(new Map());
                    try {
                      let res: ImportResult;
                      if (b.key === "bbva") {
                        res = await uploadBBVAReport(files);
                      } else {
                        res = await uploadBroker(files[0], b.key);
                      }
                      setResult(res);
                      notifyResult(res);
                    } catch (err: unknown) {
                      const msg =
                        err instanceof Error
                          ? err.message
                          : "Error desconocido";
                      setError(msg);
                      toast.error("Error de importación", { description: msg });
                    } finally {
                      setLoading(false);
                      setLoadingBroker(null);
                      e.target.value = "";
                    }
                  }}
                />
                <Button
                  variant="outline"
                  size="sm"
                  className={`w-full text-xs border ${b.color}`}
                  disabled={loading}
                  onClick={() => brokerInputRefs.current[b.key]?.click()}
                >
                  {loadingBroker === b.key ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <>
                      <span className="font-medium">{b.shortLabel}</span>
                      <span className="text-muted-foreground ml-1 hidden sm:inline">
                        {b.accept.replace(".", "").toUpperCase()}
                      </span>
                    </>
                  )}
                </Button>
              </div>
            ))}
          </div>
        </div>

        {(result?.status === "success" || result?.status === "replaced") && (
          <div className="mt-4 p-4 bg-green-500/10 border border-green-500/20 rounded-lg text-sm">
            <p className="text-green-400 font-medium flex items-center justify-center gap-2">
              <CheckCircle2 className="h-4 w-4" />
              {result.status === "replaced" ? "Reemplazado" : "Importado"} — Año
              fiscal {result.fiscal_year}
            </p>
            {result.status === "replaced" && result.message && (
              <p className="mt-1 text-yellow-400/80 text-xs">
                {result.message}
              </p>
            )}
            {result.counts && (
              <div className="mt-2 flex gap-4 justify-center text-muted-foreground text-xs">
                <span>{result.counts.dividends} dividendos</span>
                <span>{result.counts.transactions} transacciones</span>
                <span>{result.counts.capital_gains} ganancias</span>
                <span>{result.counts.casillas} casillas</span>
              </div>
            )}
            {result.issues && result.issues.length > 0 && (
              <div className="mt-3 border-t border-green-500/20 pt-3">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Supervisor de datos — {result.issues.length} aviso
                  {result.issues.length === 1 ? "" : "s"}
                </p>
                <div className="space-y-1.5 text-left">
                  {result.issues.map((issue: DataIssue) => (
                    <IssueCard
                      key={issue.id}
                      issue={resolvedIssues.get(issue.id) ?? issue}
                      onResolved={handleResolved}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {result?.status === "duplicate" && (
          <p className="mt-4 text-yellow-400 text-sm flex items-center justify-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {result.message}
          </p>
        )}

        {error && <p className="mt-4 text-destructive text-sm">{error}</p>}
      </CardContent>
    </Card>
  );
}
