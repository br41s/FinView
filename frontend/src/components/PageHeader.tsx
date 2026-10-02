"use client";

import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { QuickNav, type QuickNavPage } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { Separator } from "@/components/ui/separator";

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  subtitle: ReactNode;
  current: QuickNavPage;
  privacy: boolean;
  onTogglePrivacy: () => void;
  /** Page-specific controls; they sit on the second row and wrap down. */
  actions?: ReactNode;
  /** Extra rows under the header (status lines, badges). */
  children?: ReactNode;
  className?: string;
}

// The header every top-level page shares. The first row is identical on every
// page — title, navigation, account actions — so the buttons never move when
// you switch pages; anything a page adds goes on the rows below.
export function PageHeader({
  icon: Icon,
  title,
  subtitle,
  current,
  privacy,
  onTogglePrivacy,
  actions,
  children,
  className = "",
}: PageHeaderProps) {
  return (
    <header className={`space-y-3 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <Icon className="h-6 w-6" />
          {title}
        </h1>
        <div className="flex flex-wrap items-center gap-1">
          <QuickNav current={current} />
          <Separator orientation="vertical" className="mx-1 hidden h-4 sm:block" />
          <HeaderActions privacy={privacy} onTogglePrivacy={onTogglePrivacy} />
        </div>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="text-muted-foreground">{subtitle}</div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </header>
  );
}
