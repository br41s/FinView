'use client';

import { useState, useCallback, useEffect } from 'react';

export type Variant = 'a' | 'b';

const VARIANT_KEY = 'finview-intro-variant';

export function useVariant(defaultVariant: Variant = 'a') {
  const [variant, setVariantState] = useState<Variant>(defaultVariant);
  const [replayCount, setReplayCount] = useState(0);

  // Read from localStorage after mount to avoid SSR mismatch
  useEffect(() => {
    try {
      const stored = localStorage.getItem(VARIANT_KEY) as Variant | null;
      if (stored === 'a' || stored === 'b') setVariantState(stored);
    } catch {}
  }, []);

  const setVariant = useCallback((v: Variant) => {
    setVariantState(v);
    try { localStorage.setItem(VARIANT_KEY, v); } catch {}
    setReplayCount(c => c + 1);
  }, []);

  const replay = useCallback(() => setReplayCount(c => c + 1), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') setVariant('a');
      if (e.key === 'ArrowRight') setVariant('b');
      if (e.key === 'r' || e.key === 'R') replay();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setVariant, replay]);

  return { variant, setVariant, replayCount, replay };
}
