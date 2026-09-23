"use client";

import { signOut } from "next-auth/react";
import { Eye, EyeOff, CreditCard, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { clearAuthToken, invalidateCache } from "@/lib/api";
import { ThemeToggle } from "@/components/ThemeToggle";

interface HeaderActionsProps {
  privacy: boolean;
  onTogglePrivacy: () => void;
}

// The upper-right actions shared by every top-level page: hide/show balances,
// switch theme, jump to billing, and sign out.
export function HeaderActions({ privacy, onTogglePrivacy }: HeaderActionsProps) {
  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        onClick={onTogglePrivacy}
        aria-pressed={privacy}
        title={privacy ? "Mostrar importes" : "Ocultar importes"}
        aria-label={privacy ? "Mostrar importes" : "Ocultar importes"}
      >
        {privacy ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </Button>
      <ThemeToggle />
      <Button
        variant="ghost"
        size="icon"
        onClick={() => window.location.assign(new URL("/billing", window.location.origin))}
        title="Facturación"
        aria-label="Facturación"
      >
        <CreditCard className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => {
          clearAuthToken();
          invalidateCache();
          signOut({ callbackUrl: "/login" });
        }}
        title="Cerrar sesión"
        aria-label="Cerrar sesión"
      >
        <LogOut className="h-4 w-4" />
      </Button>
    </div>
  );
}
