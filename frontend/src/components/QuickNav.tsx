"use client";

import { useRouter } from "next/navigation";
import { BarChart3, Briefcase, Activity, Target, Landmark, Upload } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", Icon: BarChart3 },
  { href: "/portfolio", label: "Cartera", Icon: Briefcase },
  { href: "/options", label: "Derivados", Icon: Activity },
  { href: "/zonas-clave", label: "Técnico", Icon: Target },
  { href: "/alt-investments", label: "Inversiones Alt.", Icon: Landmark },
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
      <Separator orientation="vertical" className="mx-1 h-4" />
      <Tooltip>
        <TooltipTrigger
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          onClick={() => router.push("/dashboard#importar")}
        >
          <Upload className="h-4 w-4" />
        </TooltipTrigger>
        <TooltipContent>Importar datos</TooltipContent>
      </Tooltip>
    </div>
  );
}
