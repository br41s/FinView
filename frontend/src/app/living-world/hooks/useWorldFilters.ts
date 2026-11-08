import { useCallback, useState } from "react";
import { EMPTY_FILTERS, type WorldFilters } from "../model/types";

type ListKey = "assetTypes" | "archetypes" | "countries" | "brokers" | "directions" | "categories" | "severities";

/** Filter state only: what the filters *do* lives in `model/filters.ts`, where it is tested. */
export function useWorldFilters() {
  const [filters, setFilters] = useState<WorldFilters>(EMPTY_FILTERS);

  const set = useCallback((patch: Partial<WorldFilters>) => setFilters((f) => ({ ...f, ...patch })), []);

  const toggle = useCallback(<K extends ListKey>(key: K, value: WorldFilters[K][number]) => {
    setFilters((f) => {
      const list = f[key] as Array<WorldFilters[K][number]>;
      const next = list.includes(value) ? list.filter((x) => x !== value) : [...list, value];
      return { ...f, [key]: next };
    });
  }, []);

  // The window and isolate are views, not restrictions: clearing keeps them.
  const clear = useCallback(
    () => setFilters((f) => ({ ...EMPTY_FILTERS, window: f.window, isolate: f.isolate })),
    [],
  );

  return { filters, set, toggle, clear };
}
