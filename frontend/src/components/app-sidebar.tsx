"use client";

import {
  Activity,
  BarChart3,
  TrendingUp,
  Coins,
  FileText,
  LineChart,
  Upload,
  Calendar,
  CalendarRange,
  LogOut,
  CreditCard,
  Briefcase,
  Target,
} from "lucide-react";
import { signOut, useSession } from "next-auth/react";

import { clearAuthToken, invalidateCache } from "@/lib/api";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";

export type View =
  | "graficas"
  | "rendimiento"
  | "casillas"
  | "dividendos"
  | "ganancias"
  | "comparativa"
  | "importar";

interface AppSidebarProps {
  currentView: View;
  onViewChange: (view: View) => void;
  selectedYear: number | null;
  onYearChange: (year: number | null) => void;
  fiscalYears: number[];
  counts?: {
    rendimiento?: number;
    casillas?: number;
    dividendos?: number;
    ganancias?: number;
  };
}

const mainNav = [
  { key: "graficas" as const, label: "Dashboard", icon: BarChart3 },
  { key: "rendimiento" as const, label: "Rendimiento", icon: TrendingUp },
  { key: "dividendos" as const, label: "Dividendos", icon: Coins },
];

const fiscalNav = [
  { key: "casillas" as const, label: "Casillas fiscales", icon: FileText },
  { key: "ganancias" as const, label: "Ganancias de capital", icon: LineChart },
];

const analysisNav = [
  {
    key: "comparativa" as const,
    label: "Comparativa anual",
    icon: CalendarRange,
  },
];

export function AppSidebar({
  currentView,
  onViewChange,
  selectedYear,
  onYearChange,
  fiscalYears,
  counts,
}: Readonly<AppSidebarProps>) {
  const showFiscal = selectedYear !== null;
  const { data: session } = useSession();

  return (
    <Sidebar collapsible="icon" variant="sidebar">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex items-center gap-2 px-2 py-2 group-data-[collapsible=icon]:justify-center">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground text-sm font-bold shrink-0">
            FV
          </div>
          <div className="flex flex-col group-data-[collapsible=icon]:hidden">
            <span className="text-sm font-semibold">FinView</span>
            <span className="text-xs text-muted-foreground">Dashboard</span>
          </div>
        </div>
      </SidebarHeader>

      <SidebarContent>
        {/* Import — prominent CTA */}
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={currentView === "importar"}
                  onClick={() => onViewChange("importar")}
                  tooltip="Importar datos"
                  className={
                    currentView === "importar"
                      ? undefined
                      : "bg-sidebar-primary text-sidebar-primary-foreground hover:opacity-90 font-medium"
                  }
                >
                  <Upload />
                  <span>Importar</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Year Selector */}
        {fiscalYears.length > 0 && (
          <SidebarGroup>
            <SidebarGroupLabel>
              <Calendar className="mr-2 h-4 w-4" />
              Año fiscal
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <div className="px-2 group-data-[collapsible=icon]:hidden">
                <select
                  aria-label="Seleccionar año fiscal"
                  value={selectedYear ?? ""}
                  onChange={(e) =>
                    onYearChange(e.target.value ? Number(e.target.value) : null)
                  }
                  className="w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm text-foreground ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">Todos los años</option>
                  {fiscalYears.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
              <div className="hidden group-data-[collapsible=icon]:block px-1">
                <Badge
                  variant="secondary"
                  className="w-full justify-center text-xs"
                >
                  {selectedYear ?? "∞"}
                </Badge>
              </div>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* Main Navigation */}
        <SidebarGroup>
          <SidebarGroupLabel>Principal</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {mainNav.map((item) => (
                <SidebarMenuItem key={item.key}>
                  <SidebarMenuButton
                    isActive={currentView === item.key}
                    onClick={() => onViewChange(item.key)}
                    tooltip={item.label}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                    {counts?.[item.key as keyof typeof counts] !==
                      undefined && (
                      <Badge
                        variant="secondary"
                        className="ml-auto text-xs tabular-nums"
                      >
                        {counts[item.key as keyof typeof counts]}
                      </Badge>
                    )}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Cartera"
                  onClick={() => (window.location.href = "/portfolio")}
                >
                  <Briefcase />
                  <span>Cartera</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Fiscal Navigation (only when year selected) */}
        {showFiscal && (
          <SidebarGroup>
            <SidebarGroupLabel>Fiscal {selectedYear}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {fiscalNav.map((item) => (
                  <SidebarMenuItem key={item.key}>
                    <SidebarMenuButton
                      isActive={currentView === item.key}
                      onClick={() => onViewChange(item.key)}
                      tooltip={item.label}
                    >
                      <item.icon />
                      <span>{item.label}</span>
                      {counts?.[item.key as keyof typeof counts] !==
                        undefined && (
                        <Badge
                          variant="secondary"
                          className="ml-auto text-xs tabular-nums"
                        >
                          {counts[item.key as keyof typeof counts]}
                        </Badge>
                      )}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}

        {/* Analysis */}
        <SidebarGroup>
          <SidebarGroupLabel>Análisis</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {analysisNav.map((item) => (
                <SidebarMenuItem key={item.key}>
                  <SidebarMenuButton
                    isActive={currentView === item.key}
                    onClick={() => onViewChange(item.key)}
                    tooltip={item.label}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Derivados */}
        <SidebarGroup>
          <SidebarGroupLabel>Derivados</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Opciones"
                  onClick={() => (window.location.href = "/options")}
                >
                  <Activity />
                  <span>Opciones</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* Técnico */}
        <SidebarGroup>
          <SidebarGroupLabel>Técnico</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Zonas Clave"
                  onClick={() => (window.location.href = "/zonas-clave")}
                >
                  <Target />
                  <span>Zonas Clave</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border">
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip="Facturación"
              onClick={() => (window.location.href = "/billing")}
            >
              <CreditCard />
              <span className="flex items-center gap-2">
                Facturación
                <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                  {session?.user?.subscription_tier === "PRO"
                    ? "Pro"
                    : session?.user?.subscription_tier === "UNLIMITED"
                      ? "∞"
                      : "Free"}
                </Badge>
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip={session?.user?.email ?? "Cerrar sesión"}
              onClick={() => {
                clearAuthToken();
                invalidateCache();
                signOut({ callbackUrl: "/login" });
              }}
            >
              <LogOut />
              <span className="truncate">
                {session?.user?.name || session?.user?.email || "Salir"}
              </span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
