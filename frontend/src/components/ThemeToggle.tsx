"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

// Nothing to subscribe to: the store only distinguishes server/hydration
// (false) from a mounted client (true).
const subscribeNoop = () => () => {};

/**
 * Switch between light and dark.
 *
 * The theme starts as "system" and only becomes an explicit choice once this is
 * used, so a first-time visitor gets whatever their OS asks for.
 *
 * Renders a placeholder until mounted: the server cannot know the resolved
 * theme, so drawing the real icon during SSR guarantees a wrong first paint and
 * a hydration mismatch. The placeholder keeps the header from reflowing when
 * the real button arrives.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribeNoop,
    () => true,
    () => false,
  );

  if (!mounted) {
    return <div className="h-9 w-9" aria-hidden="true" />;
  }

  const isDark = resolvedTheme === "dark";
  const label = isDark ? "Cambiar a modo claro" : "Cambiar a modo oscuro";

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-pressed={isDark}
      title={label}
      aria-label={label}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
