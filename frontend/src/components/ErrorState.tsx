import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Full-width "could not load" state with a retry button. Shared by the
 * dashboard and the portfolio page, which used to carry identical copies.
 */
export function ErrorState({
  message,
  onRetry,
}: Readonly<{ message: string; onRetry: () => void }>) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
      <div className="rounded-full bg-destructive/10 p-4">
        <AlertCircle className="h-8 w-8 text-destructive" />
      </div>
      <div>
        <h3 className="text-lg font-medium mb-1">Error al cargar datos</h3>
        <p className="text-sm text-muted-foreground max-w-md">{message}</p>
      </div>
      <Button variant="outline" onClick={onRetry}>
        Reintentar
      </Button>
    </div>
  );
}
