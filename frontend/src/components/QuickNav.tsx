"use client";

import { useRouter } from "next/navigation";
import { BarChart3, Briefcase, Activity, Target } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", Icon: BarChart3 },
  { href: "/portfolio", label: "Cartera", Icon: Briefcase },
  { href: "/options", label: "Derivados", Icon: Activity },
  { href: "/zonas-clave", label: "Técnico", Icon: Target },
] as const;

export type QuickNavPage = (typeof NAV_ITEMS)[number]["href"];

interface QuickNavProps {
  current: QuickNavPage;
}

export function QuickNav({ current }: QuickNavProps) {
  const router = useRouter();
  return (
    <div className="flex items-center gap-1">
      {NAV_ITEMS.map(({ href, label, Icon }) => (
        <Tooltip key={href}>
          <TooltipTrigger
            className={
              href === current
                ? "inline-flex h-8 w-8 items-center justify-center rounded-md text-foreground"
                : "inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            }
            aria-current={href === current ? "page" : undefined}
            onClick={() => router.push(href)}
          >
            <Icon className="h-4 w-4" />
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
