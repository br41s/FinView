import type { Metadata } from "next";
import LivingWorldClient from "./LivingWorldClient";

export const metadata: Metadata = {
  title: "Mundo vivo · FinView",
  description: "Tu cartera como un pueblo en 3D.",
  robots: { index: false },
};

export default async function LivingWorldPage({
  searchParams,
}: Readonly<{ searchParams: Promise<Record<string, string | string[] | undefined>> }>) {
  const { demo } = await searchParams;
  return <LivingWorldClient demo={demo !== undefined} />;
}
