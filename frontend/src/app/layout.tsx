import type { Metadata } from "next";
import "./globals.css";
import { Geist, Fraunces, JetBrains_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/components/auth-provider";
import { InstrumentDrawerProvider } from "@/components/InstrumentDrawer";
import { cn } from "@/lib/utils";

const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });
const fraunces = Fraunces({ subsets: ["latin"], axes: ["opsz"], variable: "--fv-font-fraunces" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--fv-font-jetbrains" });

export const metadata: Metadata = {
  title: "FinView",
  description: "Personal investment dashboard — Spanish IRPF fiscal engine",
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
        <AuthProvider>
          <TooltipProvider>
            <InstrumentDrawerProvider>{children}</InstrumentDrawerProvider>
          </TooltipProvider>
          <Toaster richColors position="bottom-right" />
        </AuthProvider>
      </body>
    </html>
  );
}
