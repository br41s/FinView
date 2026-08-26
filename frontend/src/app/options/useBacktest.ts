"use client";

import { useCallback, useState } from "react";

import { api } from "@/lib/api";

import type { BacktestSignal, BacktestStats, Calibration } from "./types";

/**
 * The backtest tab's data, lifted out of OptionsPage.
 *
 * Five of the page's `useState` calls and both loaders served only this one
 * tab. They stay here in the parent rather than inside the tab component
 * because Radix unmounts inactive `TabsContent`: owning them in the tab would
 * refetch all three endpoints every time the user switched away and back. The
 * tab is still lazy — nothing loads until the trigger asks for it the first
 * time.
 */
export interface Backtest {
  signals: BacktestSignal[];
  stats: BacktestStats | null;
  calibration: Calibration | null;
  loading: boolean;
  evaluating: boolean;
  load: () => Promise<void>;
  evaluate: () => Promise<void>;
}

export function useBacktest(): Backtest {
  const [signals, setSignals] = useState<BacktestSignal[]>([]);
  const [stats, setStats] = useState<BacktestStats | null>(null);
  const [calibration, setCalibration] = useState<Calibration | null>(null);
  const [loading, setLoading] = useState(false);
  const [evaluating, setEvaluating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sigs, st, calib] = await Promise.all([
        api.options.backtestSignals({ days: 30 }) as Promise<BacktestSignal[]>,
        api.options.backtestStats() as Promise<BacktestStats>,
        api.options.backtestCalibration(30) as Promise<Calibration>,
      ]);
      setSignals(sigs);
      setStats(st);
      setCalibration(calib);
    } catch (e) {
      console.error("Failed to load backtest data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  const evaluate = useCallback(async () => {
    setEvaluating(true);
    try {
      await api.options.backtestEvaluate();
      await load();
    } finally {
      setEvaluating(false);
    }
  }, [load]);

  return { signals, stats, calibration, loading, evaluating, load, evaluate };
}
