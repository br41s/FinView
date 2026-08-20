"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * Mounts next-themes so the `dark` class actually reaches <html>.
 *
 * Without this the whole dark palette was dead code: globals.css defined a full
 * `.dark` block, next-themes was installed, and `useTheme()` was consumed by
 * Sonner and PriceChart — but nothing ever set the class, so the app was
 * permanently light and both components always took the light branch.
 *
 * attribute="class" matches the `@custom-variant dark (&:is(.dark *))` that
 * globals.css declares for Tailwind. defaultTheme="system" follows the OS until
 * the user picks explicitly; the choice then persists in localStorage.
 *
 * disableTransitionOnChange stops every colour-transitioning element from
 * animating at once during a switch, which reads as a smear rather than a theme
 * change. The root layout already sets suppressHydrationWarning on <html>,
 * which next-themes needs because it writes the class before React hydrates.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  );
}
