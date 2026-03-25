import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinView",
  description: "Personal investment dashboard — Spanish IRPF fiscal engine",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
