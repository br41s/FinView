"use client";

import { useState, useCallback } from "react";
import { uploadTRReport, uploadDGReport } from "@/lib/api";
import type { ImportResult } from "@/lib/types";

function detectBroker(filename: string): "tr" | "degiro" | null {
  const lower = filename.toLowerCase();
  if (lower.startsWith("dg-") || lower.includes("degiro") || lower.includes("informe anual")) return "degiro";
  if (lower.startsWith("tr-") || lower.includes("trade republic") || lower.includes("tax_report")) return "tr";
  return null;
}

export function FileUpload({ onImported }: Readonly<{ onImported: () => void }>) {
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Solo se aceptan archivos PDF");
        return;
      }
      const broker = detectBroker(file.name);
      if (!broker) {
        setError("No se pudo detectar el broker. El archivo debe empezar por 'TR-' o 'DG-'.");
        return;
      }
      setLoading(true);
      setError(null);
      setResult(null);
      try {
        const upload = broker === "degiro" ? uploadDGReport : uploadTRReport;
        const res = await upload(file);
        setResult(res);
        if (res.status === "success") onImported();
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
      role="button"
      tabIndex={0}
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
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          (e.currentTarget.querySelector("input[type=file]") as HTMLInputElement)?.click();
        }
      }}
    >
      <div className="mb-3 text-4xl">📄</div>
      <p className="text-neutral-400 mb-3">
        Arrastra aquí un PDF de Trade Republic o DEGIRO
      </p>
      <label className="inline-block px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg cursor-pointer text-sm font-medium transition-colors">
        Seleccionar archivo
        <input
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
          }}
        />
      </label>

      {loading && <p className="mt-4 text-blue-400 animate-pulse">Procesando PDF...</p>}

      {result?.status === "success" && (
        <div className="mt-4 p-4 bg-green-900/30 border border-green-800 rounded-lg text-sm">
          <p className="text-green-400 font-medium">
            ✓ Importado — Año fiscal {result.fiscal_year}
          </p>
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
