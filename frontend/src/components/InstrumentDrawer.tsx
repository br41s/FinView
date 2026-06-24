"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";

import { api, type OhlcBar } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { CHART_SCOPES, sliceOhlc, type ChartScope } from "@/lib/chartMarkers";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// Which lens to open the drawer on. "precio" is the only one wired in Phase 2;
// "opciones"/"zonas" are placeholders until Phase 3 fills them in place.
export type InstrumentTab = "precio" | "opciones" | "zonas";

interface OpenOpts {
  isin?: string;
  name?: string;
  tab?: InstrumentTab;
}

interface InstrumentDrawerContextValue {
  openInstrument: (symbol: string, opts?: OpenOpts) => void;
}

const InstrumentDrawerContext = createContext<InstrumentDrawerContextValue | null>(null);

export function useInstrumentDrawer(): InstrumentDrawerContextValue {
  const ctx = useContext(InstrumentDrawerContext);
  if (!ctx) {
    throw new Error("useInstrumentDrawer must be used within InstrumentDrawerProvider");
  }
  return ctx;
}

/**
 * Global, ticker-keyed instrument drawer. Any section can call
 * `openInstrument(symbol)` to slide it open. Each tab is a self-contained
 * `{ symbol }` component so it can later be promoted into a `/ticker/[symbol]`
 * page (roadmap B) without rework.
 */
export function InstrumentDrawerProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [symbol, setSymbol] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [tab, setTab] = useState<InstrumentTab>("precio");
  const [ownedTickers, setOwnedTickers] = useState<Set<string> | null>(null);

  const openInstrument = useCallback((sym: string, opts?: OpenOpts) => {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    setSymbol(s);
    setName(opts?.name ?? "");
    setTab(opts?.tab ?? "precio");
    setOpen(true);
  }, []);

  // Lazy-load holdings once (cached) to show an "En cartera" badge.
  useEffect(() => {
    if (!open || ownedTickers !== null) return;
    api.portfolio
      .positions(true)
      .then((pos) => {
        const p = pos as { ticker: string | null }[];
        setOwnedTickers(
          new Set(p.filter((x) => x.ticker).map((x) => x.ticker!.toUpperCase())),
        );
      })
      .catch(() => setOwnedTickers(new Set()));
  }, [open, ownedTickers]);

  const owned = symbol != null && (ownedTickers?.has(symbol) ?? false);
  const ctx = useMemo(() => ({ openInstrument }), [openInstrument]);

  return (
    <InstrumentDrawerContext.Provider value={ctx}>
      {children}
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="right"
          className="w-full gap-0 p-0 data-[side=right]:sm:max-w-2xl"
        >
          <SheetHeader className="border-b px-5 py-4">
            <SheetTitle className="flex items-center gap-2 text-lg font-semibold">
              {symbol ?? "—"}
              {owned && <Badge variant="secondary">En cartera</Badge>}
            </SheetTitle>
            {name ? (
              <SheetDescription>{name}</SheetDescription>
            ) : (
              <SheetDescription className="sr-only">
                Detalle del instrumento {symbol}
              </SheetDescription>
            )}
          </SheetHeader>

          {symbol && (
            <Tabs
              value={tab}
              onValueChange={(v) => setTab(v as InstrumentTab)}
              className="min-h-0 flex-1 gap-0 overflow-hidden px-5 py-3"
            >
              <TabsList>
                <TabsTrigger value="precio">Precio</TabsTrigger>
                <TabsTrigger value="opciones">Opciones</TabsTrigger>
                <TabsTrigger value="zonas">Zonas</TabsTrigger>
              </TabsList>

              <TabsContent value="precio" className="overflow-auto pt-3">
                <PrecioTab symbol={symbol} />
              </TabsContent>

              <TabsContent value="opciones" className="pt-3">
                <ComingSoon
                  label="Opciones"
                  phase="Fase 3"
                  onOpenFull={() => {
                    setOpen(false);
                    router.push(`/options?ticker=${encodeURIComponent(symbol)}`);
                  }}
                  cta="Abrir en Opciones"
                />
              </TabsContent>

              <TabsContent value="zonas" className="pt-3">
                <ComingSoon
                  label="Zonas Clave"
                  phase="Fase 3"
                  onOpenFull={() => {
                    setOpen(false);
                    router.push(`/zonas-clave?ticker=${encodeURIComponent(symbol)}`);
                  }}
                  cta="Abrir en Zonas Clave"
                />
              </TabsContent>
            </Tabs>
          )}
        </SheetContent>
      </Sheet>
    </InstrumentDrawerContext.Provider>
  );
}

function PrecioTab({ symbol }: { symbol: string }) {
  const [bars, setBars] = useState<OhlcBar[] | null>(null);
  const [scope, setScope] = useState<ChartScope>("1A");

  useEffect(() => {
    let cancelled = false;
    setBars(null);
    api.charts
      .priceHistory(symbol, "max")
      .then((b) => {
        if (!cancelled) setBars(b);
      })
      .catch(() => {
        if (!cancelled) setBars([]);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  if (bars === null) return <Skeleton className="h-[360px] w-full" />;
  if (bars.length === 0) {
    return (
      <div className="flex h-[360px] items-center justify-center text-sm text-muted-foreground">
        Sin datos de precio para {symbol}.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-0.5">
        {CHART_SCOPES.map((s) => (
          <button
            key={s}
            onClick={() => setScope(s)}
            className={`rounded px-2 py-0.5 text-xs font-medium transition-colors ${
              scope === s
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            {s}
          </button>
        ))}
      </div>
      <PriceChart data={sliceOhlc(bars, scope)} height={360} />
    </div>
  );
}

function ComingSoon({
  label,
  phase,
  onOpenFull,
  cta,
}: {
  label: string;
  phase: string;
  onOpenFull: () => void;
  cta: string;
}) {
  return (
    <div className="flex h-[260px] flex-col items-center justify-center gap-3 text-center">
      <p className="text-sm text-muted-foreground">
        {label} en el drawer — {phase}.
      </p>
      <Button variant="outline" size="sm" onClick={onOpenFull} className="gap-1">
        {cta}
        <ArrowRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}
