"use client";

import { useState, useCallback } from "react";
import { uploadTRReport, uploadDGReport, uploadIBKRReport, uploadINGReport, uploadBBVAReport, uploadEToroReport } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

function detectBroker(filename: string): "tr" | "degiro" | "ibkr" | "ing" | "bbva" | "etoro" | null {
  const lower = filename.toLowerCase();
  if (lower.startsWith("dg-") || lower.includes("degiro") || lower.includes("informe anual")) return "degiro";
  if (lower.startsWith("tr-") || lower.includes("trade republic") || lower.includes("tax_report")) return "tr";
  if (lower.startsWith("ibkr") || lower.includes("interactive") || lower.includes("u1104")) return "ibkr";
  if (lower.includes("ing") || lower.includes("información fiscal") || lower.includes("informacion fiscal")) return "ing";
  if (lower.includes("bbva")) return "bbva";
  if (lower.includes("etoro") || lower.includes("account-statement")) return "etoro";
  return null;
}

export function FileUpload({ onImported }: Readonly<{ onImported: () => void }>) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = useCallback(
    async (files: File[]) => {
      for (const f of files) {
        const ext = f.name.toLowerCase();
        if (!ext.endsWith(".pdf") && !ext.endsWith(".csv") && !ext.endsWith(".xlsx")) {
          setError("Solo se aceptan archivos PDF, CSV o XLSX");
          return;
        }
      }

      // Check if any file is BBVA — if so, send all together
      const brokers = files.map((f) => detectBroker(f.name));
      const hasBBVA = brokers.some((b) => b === "bbva");

      if (hasBBVA) {
        // BBVA multi-file upload
        const bbvaFiles = files.filter((f) => detectBroker(f.name) === "bbva");
        if (bbvaFiles.length === 0 || bbvaFiles.length > 3) {
          setError("BBVA: selecciona entre 1 y 3 archivos PDF del mismo año");
          return;
        }
        setLoading(true);
        setError(null);
        setResult(null);
        try {
          const res = await uploadBBVAReport(bbvaFiles);
          setResult(res);
          if (res.status === "success" || res.status === "replaced") onImported();
        } catch (e: unknown) {
          setError(e instanceof Error ? e.message : "Error desconocido");
        } finally {
          setLoading(false);
        }
        return;
      }

      // Single-file brokers
      const file = files[0];
      const broker = detectBroker(file.name);
      if (!broker) {
        setError("No se pudo detectar el broker. El archivo debe contener 'TR-', 'DG-', 'IBKR', 'ING', 'BBVA' o 'eToro'.");
        return;
      }
      setLoading(true);
      setError(null);
      setResult(null);
      try {
        const uploadMap = { degiro: uploadDGReport, tr: uploadTRReport, ibkr: uploadIBKRReport, ing: uploadINGReport, etoro: uploadEToroReport } as const;
        const upload = uploadMap[broker as keyof typeof uploadMap];
        const res = await upload(file);
        setResult(res);
        if (res.status === "success" || res.status === "replaced") onImported();
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Error desconocido");
      } finally {
        setLoading(false);
      }
    },
    [onImported]
  );

  return (
    <div
      role="region"
      aria-label="Zona de carga de archivos"
      className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
        dragging ? "border-blue-500 bg-blue-500/10" : "border-neutral-700 hover:border-neutral-500"
      }`}
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
      <div className="mb-3 text-4xl">📄</div>
      <p className="text-neutral-400 mb-3">
        Arrastra aquí archivos de Trade Republic (PDF), DEGIRO (PDF), IBKR (CSV), ING (PDF), BBVA (1-3 PDFs) o eToro (XLSX)
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
      <button
        type="button"
        className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg cursor-pointer text-sm font-medium transition-colors"
        onClick={() => document.getElementById("file-upload")?.click()}
      >
        Seleccionar archivos
      </button>

      {loading && <p className="mt-4 text-blue-400 animate-pulse">Procesando archivo...</p>}

      {(result?.status === "success" || result?.status === "replaced") && (
        <div className="mt-4 p-4 bg-green-900/30 border border-green-800 rounded-lg text-sm">
          <p className="text-green-400 font-medium">
            {result.status === "replaced" ? "↻" : "✓"} {result.status === "replaced" ? "Reemplazado" : "Importado"} — Año fiscal {result.fiscal_year}
          </p>
          {result.status === "replaced" && result.message && (
            <p className="mt-1 text-yellow-400/80 text-xs">{result.message}</p>
          )}
          {result.counts && (
            <div className="mt-2 flex gap-4 justify-center text-neutral-300">
              <span>{result.counts.dividends} dividendos</span>
              <span>{result.counts.transactions} transacciones</span>
              <span>{result.counts.capital_gains} ganancias</span>
              <span>{result.counts.casillas} casillas</span>
            </div>
          )}
        </div>
      )}

      {result?.status === "duplicate" && (
        <p className="mt-4 text-yellow-400 text-sm">⚠ {result.message}</p>
      )}

      {error && <p className="mt-4 text-red-400 text-sm">✗ {error}</p>}
    </div>
  );
}
