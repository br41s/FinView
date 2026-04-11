"use client";

import { Suspense, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { CreditCard, ExternalLink, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { LoadingDots } from "@/components/loading-dots";

interface Subscription {
  tier: string;
  status: string | null;
  label: string;
  max_accounts: number;
  max_imports_per_month: number;
  current_period_end: string | null;
  has_stripe_subscription: boolean;
}

const tierBadgeColor: Record<string, string> = {
  FREE: "bg-zinc-700 text-zinc-200",
  PRO: "bg-blue-600 text-white",
  UNLIMITED: "bg-purple-600 text-white",
};

export default function BillingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <LoadingDots text="Cargando facturación" />
        </div>
      }
    >
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const { data: session } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const success = searchParams.get("success");
  const canceled = searchParams.get("canceled");

  const [sub, setSub] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);

  useEffect(() => {
    api.billing
      .subscription()
      .then((data) => setSub(data as Subscription))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handlePortal() {
    setPortalLoading(true);
    try {
      const { url } = await api.billing.portal();
      window.location.href = url;
    } catch {
      setPortalLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingDots text="Cargando facturación" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-3xl font-bold mb-6">Facturación</h1>

      {success && (
        <div className="mb-6 rounded-lg bg-green-500/10 border border-green-500/20 p-4 text-green-400">
          ¡Tu suscripción se ha activado correctamente!
        </div>
      )}

      {canceled && (
        <div className="mb-6 rounded-lg bg-yellow-500/10 border border-yellow-500/20 p-4 text-yellow-400">
          El pago fue cancelado. Tu plan no ha cambiado.
        </div>
      )}

      {/* Current plan card */}
      <Card className="mb-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <CreditCard className="h-5 w-5" />
            Tu plan
          </CardTitle>
          <Badge className={tierBadgeColor[sub?.tier || "FREE"]}>
            {sub?.label || "Free"}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-muted-foreground">Cuentas de broker</p>
              <p className="font-medium">Máx. {sub?.max_accounts || 2}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Importaciones/mes</p>
              <p className="font-medium">
                Máx. {sub?.max_imports_per_month || 5}
              </p>
            </div>
            {sub?.status && (
              <div>
                <p className="text-muted-foreground">Estado</p>
                <p className="font-medium capitalize">
                  {sub.status.toLowerCase().replace("_", " ")}
                </p>
              </div>
            )}
            {sub?.current_period_end && (
              <div>
                <p className="text-muted-foreground">Próxima renovación</p>
                <p className="font-medium">
                  {new Date(sub.current_period_end).toLocaleDateString("es-ES")}
                </p>
              </div>
            )}
          </div>

          <div className="flex gap-3 pt-2">
            {sub?.has_stripe_subscription ? (
              <Button
                onClick={handlePortal}
                disabled={portalLoading}
                variant="outline"
              >
                <ExternalLink className="mr-2 h-4 w-4" />
                {portalLoading ? "Redirigiendo..." : "Gestionar suscripción"}
              </Button>
            ) : (
              <Button onClick={() => router.push("/pricing")}>
                <Sparkles className="mr-2 h-4 w-4" />
                Mejorar plan
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Account info card */}
      <Card>
        <CardHeader>
          <CardTitle>Cuenta</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Email</span>
            <span>{session?.user?.email}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted-foreground">Nombre</span>
            <span>{session?.user?.name}</span>
          </div>
        </CardContent>
      </Card>

      <Button variant="ghost" className="mt-6" onClick={() => router.push("/")}>
        Volver al dashboard
      </Button>
    </div>
  );
}
