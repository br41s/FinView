import type { ReactNode } from "react";

export type SortDir = "asc" | "desc";

/**
 * Clickable table header that shows the active sort arrow. Module-level on
 * purpose: DividendsTable and DividendYieldTable used to define it inside the
 * component body, so React saw a new component type on every render and
 * remounted every header cell (react-hooks/static-components).
 */
export function SortHeader<K extends string>({
  k,
  sortKey,
  sortDir,
  onSort,
  children,
  align = "right",
  className,
}: Readonly<{
  k: K;
  sortKey: K;
  sortDir: SortDir;
  onSort: (key: K) => void;
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
}>) {
  const active = sortKey === k;
  return (
    <th
      className={`py-2 cursor-pointer select-none hover:text-foreground transition-colors ${className ?? ""} ${align === "left" ? "text-left" : "text-right"}`}
      onClick={() => onSort(k)}
    >
      <span className={active ? "text-foreground" : ""}>
        {children} {active ? (sortDir === "asc" ? "↑" : "↓") : ""}
      </span>
    </th>
  );
}
