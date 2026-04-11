"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Check } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const PLANS = [
  {
    tier: "FREE",
    name: "Free",
    price: "0 €",
    period: "para siempre",
    features: [
      "2 cuentas de broker",
      "5 importaciones al mes",
      "Dashboard fiscal básico",
      "Casillas IRPF",
    ],
    cta: "Plan actual",
    priceId: null,
  },
  {
    tier: "PRO",
    name: "Pro",
    price: "9.99 €",
    period: "/mes",
    popular: true,
    features: [
      "10 cuentas de broker",
      "50 importaciones al mes",
      "Dashboard fiscal completo",
      "FIFO cross-broker",
      "Exportación CSV",
      "Comparativa anual",
    ],
    cta: "Empezar con Pro",
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_PRO || "",
  },
  {
    tier: "UNLIMITED",
    name: "Unlimited",
    price: "19.99 €",
    period: "/mes",
    features: [
      "Cuentas ilimitadas",
      "Importaciones ilimitadas",
      "Todo lo de Pro",
      "Soporte prioritario",
      "Acceso anticipado a nuevas funciones",
    ],
    cta: "Empezar con Unlimited",
    priceId: process.env.NEXT_PUBLIC_STRIPE_PRICE_UNLIMITED || "",
  },
];

export default function PricingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <p className="text-muted-foreground">Cargando...</p>
        </div>
      }
    >
      <PricingContent />
    </Suspense>
  );
}

function PricingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const success = searchParams.get("success");
  const canceled = searchParams.get("canceled");
  const [loading, setLoading] = useState<string | null>(null);

  async function handleCheckout(priceId: string, tier: string) {
    if (!priceId) return;
    setLoading(tier);
    try {
      const { url } = await api.billing.checkout(priceId);
      window.location.href = url;
    } catch {
      setLoading(null);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-6">
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold">Planes y precios</h1>
        <p className="mt-2 text-muted-foreground">
          Elige el plan que mejor se adapte a tus necesidades fiscales
        </p>
      </div>

      {success && (
        <div className="mb-6 rounded-lg bg-green-500/10 border border-green-500/20 p-4 text-green-400">
          ¡Suscripción activada! Redirigiendo al dashboard...
          <script
            dangerouslySetInnerHTML={{
              __html: `setTimeout(function(){window.location.href='/'},2000)`,
            }}
          />
        </div>
      )}

      {canceled && (
        <div className="mb-6 rounded-lg bg-yellow-500/10 border border-yellow-500/20 p-4 text-yellow-400">
          Pago cancelado. Puedes elegir un plan cuando quieras.
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-3 max-w-5xl w-full">
        {PLANS.map((plan) => (
          <Card
            key={plan.tier}
            className={`relative flex flex-col ${plan.popular ? "border-primary ring-2 ring-primary/20" : ""}`}
          >
            {plan.popular && (
              <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">
                Más popular
              </Badge>
            )}
            <CardHeader className="text-center">
              <CardTitle className="text-xl">{plan.name}</CardTitle>
              <div className="mt-2">
                <span className="text-3xl font-bold">{plan.price}</span>
                <span className="text-muted-foreground">{plan.period}</span>
              </div>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col justify-between gap-6">
              <ul className="space-y-3">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-sm">
                    <Check className="h-4 w-4 text-primary shrink-0" />
                    {f}
                  </li>
                ))}
              </ul>
              <Button
                className="w-full"
                variant={plan.popular ? "default" : "outline"}
                disabled={!plan.priceId || loading === plan.tier}
                onClick={() =>
                  plan.priceId && handleCheckout(plan.priceId, plan.tier)
                }
              >
                {loading === plan.tier ? "Redirigiendo..." : plan.cta}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Button variant="ghost" className="mt-8" onClick={() => router.push("/")}>
        Volver al dashboard
      </Button>
    </div>
  );
}
