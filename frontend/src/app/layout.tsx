import type { Metadata } from "next";
import "./globals.css";
import { Geist, Fraunces, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/components/auth-provider";
import { ThemeProvider } from "@/components/theme-provider";
import { cn } from "@/lib/utils";
import { SITE_URL } from "@/lib/site";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });
const fraunces = Fraunces({ subsets: ["latin"], axes: ["opsz"], variable: "--fv-font-fraunces" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--fv-font-jetbrains" });

// metadataBase makes every relative OG/canonical URL resolve to the public
// origin. Without it Next silently drops relative social-card URLs, so shared
// links render as bare URLs with no title or description.
//
// Deliberately no `title.template`: the blog's MDX titles already end in
// "— FinView", and a template would double the suffix.
//
// Deliberately no root `alternates.canonical`: metadata is inherited, so a
// canonical pointing at "/" would appear on all 58 articles and tell search
// engines each one duplicates the homepage. Canonicals belong per page.
//
// openGraph carries only the genuinely site-wide fields. Title, description and
// url are omitted so each page supplies its own instead of inheriting these.
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: "FinView",
  description: "Personal investment dashboard — Spanish IRPF fiscal engine",
  openGraph: {
    type: "website",
    siteName: "FinView",
    locale: "es_ES",
  },
  twitter: {
    card: "summary_large_image",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="es"
      className={cn("font-sans", geist.variable, fraunces.variable, jetbrainsMono.variable)}
      suppressHydrationWarning
    >
      <body className="min-h-screen bg-background text-foreground antialiased">
        <ThemeProvider>
          <AuthProvider>
            <TooltipProvider>{children}</TooltipProvider>
            <Toaster richColors position="bottom-right" />
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
