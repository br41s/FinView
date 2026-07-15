"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Building2,
  Plus,
  Pencil,
  Trash2,
  X,
  Landmark,
  TrendingUp,
  Wallet,
  PiggyBank,
  Search,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

import {
  api,
  type AltCatalogResult,
  type AltCatalogSort,
  type AltInvestment,
  type AltInvestmentInput,
  type AltInvestmentType,
  type AltSummary,
} from "@/lib/api";
import { formatEur } from "@/lib/format";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { QuickNav } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";

const TYPE_LABELS: Record<AltInvestmentType, string> = {
  PRIVATE_EQUITY: "Private Equity",
  VENTURE_CAPITAL: "Venture Capital",
  REAL_ESTATE: "Real Estate",
  HEDGE_FUND: "Hedge Fund",
  STRUCTURED_PRODUCT: "Producto Estructurado",
  OTHER: "Otro",
};

const TYPE_OPTIONS = Object.entries(TYPE_LABELS) as [AltInvestmentType, string][];

const EMPTY_FORM: AltInvestmentInput = {
  name: "",
  type: "PRIVATE_EQUITY",
  status: "ACTIVE",
  manager: "",
  vintage_year: null,
  geography: "",
  currency: "EUR",
  committed_capital: 0,
  called_capital: 0,
  distributed_capital: 0,
  current_nav: 0,
  notes: "",
};

function fmtMultiple(v: number | null): string {
  return v === null ? "—" : `${v.toFixed(2)}x`;
}

function fmtCompactEur(v: number | null): string {
  if (v === null) return "—";
  if (v >= 1e9) return `€${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `€${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `€${(v / 1e3).toFixed(0)}k`;
  return `€${v.toFixed(0)}`;
}

export default function AltInvestmentsPage() {
  const { privacy, togglePrivacy } = usePrivacyToggle();
  const [items, setItems] = useState<AltInvestment[]>([]);
  const [summary, setSummary] = useState<AltSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<AltInvestmentInput>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // Catalog search (CNMV)
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<AltCatalogResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [sort, setSort] = useState<AltCatalogSort>("name");
  const [minSize, setMinSize] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, sum] = await Promise.all([
        api.altInvestments.list(),
        api.altInvestments.summary(),
      ]);
      setItems(list);
      setSummary(sum);
    } catch (e) {
      toast.error(`Error al cargar: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Debounced catalog search / browse. Fires when the query is long enough OR a
  // filter/sort is active (so you can browse "largest funds" without a name).
  useEffect(() => {
    const q = query.trim();
    const minNum = minSize ? Number(minSize) * 1_000_000 : undefined; // input is €M
    const browsing = sort !== "name" || minNum !== undefined;
    if (q.length < 2 && !browsing) {
      setResults([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    const t = setTimeout(async () => {
      try {
        const res = await api.altInvestments.search({
          q,
          sort,
          min_fund_size: minNum,
        });
        setResults(res);
        setSearchOpen(true);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, sort, minSize]);

  function openFromCatalog(r: AltCatalogResult) {
    setEditingId(null);
    setForm({
      ...EMPTY_FORM,
      name: r.name,
      type: r.type,
      manager: r.manager,
      isin: r.isin,
      currency: "EUR",
    });
    setFormOpen(true);
    setSearchOpen(false);
    setQuery("");
    setResults([]);
    setSort("name");
    setMinSize("");
  }

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormOpen(true);
  }

  function openEdit(inv: AltInvestment) {
    setEditingId(inv.id);
    setForm({
      name: inv.name,
      type: inv.type,
      status: inv.status,
      manager: inv.manager,
      vintage_year: inv.vintage_year,
      geography: inv.geography,
      currency: inv.currency,
      committed_capital: inv.committed_capital,
      called_capital: inv.called_capital,
      distributed_capital: inv.distributed_capital,
      current_nav: inv.current_nav,
      notes: inv.notes,
    });
    setFormOpen(true);
  }

  async function handleSave() {
    if (!form.name.trim()) {
      toast.error("El nombre es obligatorio");
      return;
    }
    setSaving(true);
    try {
      if (editingId === null) {
        await api.altInvestments.create(form);
        toast.success("Inversión añadida");
      } else {
        await api.altInvestments.update(editingId, form);
        toast.success("Inversión actualizada");
      }
      setFormOpen(false);
      await load();
    } catch (e) {
      toast.error(`Error al guardar: ${e instanceof Error ? e.message : e}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(inv: AltInvestment) {
    if (!confirm(`¿Eliminar "${inv.name}"?`)) return;
    try {
      await api.altInvestments.delete(inv.id);
      toast.success("Inversión eliminada");
      await load();
    } catch (e) {
      toast.error(`Error al eliminar: ${e instanceof Error ? e.message : e}`);
    }
  }

  function setField<K extends keyof AltInvestmentInput>(
    key: K,
    value: AltInvestmentInput[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Landmark className="h-6 w-6" />
            Inversiones Alternativas
          </h1>
          <p className="text-muted-foreground">
            Private equity, venture capital y real estate de banca privada
          </p>
        </div>
        <div className="flex items-center gap-3">
          <HeaderActions privacy={privacy} onTogglePrivacy={togglePrivacy} />
          <QuickNav current="/alt-investments" />
          <Button size="sm" onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" /> Añadir
          </Button>
        </div>
      </div>

      {/* Catalog search (CNMV) */}
      <div className="relative">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setSearchOpen(true)}
              placeholder="Buscar fondo CNMV por nombre o ISIN…"
              className="pl-9"
              aria-label="Buscar en el catálogo CNMV"
            />
            {searching && (
              <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
            )}
          </div>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as AltCatalogSort)}
            aria-label="Ordenar"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <option value="name">Relevancia</option>
            <option value="fund_size_desc">Mayor patrimonio</option>
            <option value="nav_desc">Mayor NAV</option>
            <option value="nav_asc">Menor NAV</option>
          </select>
          <Input
            type="number"
            inputMode="numeric"
            value={minSize}
            onChange={(e) => setMinSize(e.target.value)}
            placeholder="Patrim. mín. (€M)"
            aria-label="Patrimonio mínimo en millones de euros"
            className="sm:w-40"
          />
        </div>
        {searchOpen &&
          (query.trim().length >= 2 || sort !== "name" || minSize !== "") && (
            <div className="absolute z-20 mt-1 max-h-96 w-full overflow-auto rounded-md border bg-popover shadow-md">
              {results.length === 0 && !searching ? (
                <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                  Sin resultados. Puedes añadirlo manualmente con “Añadir”.
                </div>
              ) : (
                results.map((r) => (
                  <button
                    key={`${r.source}-${r.isin ?? r.name}`}
                    type="button"
                    onClick={() => openFromCatalog(r)}
                    className="flex w-full items-start justify-between gap-3 border-b px-3 py-2 text-left last:border-b-0 hover:bg-accent"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{r.name}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {r.manager}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-0.5">
                      <Badge variant="outline" className="text-[10px]">
                        {TYPE_LABELS[r.type]}
                      </Badge>
                      <span className="text-[10px] tabular-nums text-muted-foreground">
                        {r.nav !== null && `NAV ${r.nav.toFixed(2)}`}
                        {r.nav !== null && r.fund_size !== null && " · "}
                        {r.fund_size !== null && `Pat. ${fmtCompactEur(r.fund_size)}`}
                      </span>
                      {r.isin && (
                        <span className="font-mono text-[10px] text-muted-foreground">
                          {r.isin}
                        </span>
                      )}
                    </div>
                  </button>
                ))
              )}
            </div>
          )}
      </div>

      {/* Summary cards */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : summary && summary.count > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            icon={<Wallet className="h-4 w-4" />}
            label="Comprometido"
            value={formatEur(summary.total_committed)}
            sub={`Sin desembolsar: ${formatEur(summary.total_unfunded)}`}
          />
          <StatCard
            icon={<PiggyBank className="h-4 w-4" />}
            label="Desembolsado (called)"
            value={formatEur(summary.total_called)}
            sub={`Distribuido: ${formatEur(summary.total_distributed)}`}
          />
          <StatCard
            icon={<Building2 className="h-4 w-4" />}
            label="NAV actual"
            value={formatEur(summary.total_nav)}
            sub={`Valor total: ${formatEur(summary.total_value)}`}
          />
          <StatCard
            icon={<TrendingUp className="h-4 w-4" />}
            label="TVPI / DPI"
            value={`${fmtMultiple(summary.overall_tvpi)} / ${fmtMultiple(summary.overall_dpi)}`}
            sub={`RVPI: ${fmtMultiple(summary.overall_rvpi)}`}
          />
        </div>
      ) : null}

      {/* Allocation by type */}
      {!loading && summary && summary.by_type.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Asignación por tipo (NAV)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {summary.by_type.map((slice) => (
              <div key={slice.label} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span>
                    {TYPE_LABELS[slice.label as AltInvestmentType] ?? slice.label}
                  </span>
                  <span className="tabular-nums text-muted-foreground">
                    {formatEur(slice.value)} · {slice.pct.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${slice.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Inline add/edit form */}
      {formOpen && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">
              {editingId === null ? "Nueva inversión" : "Editar inversión"}
            </CardTitle>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setFormOpen(false)}
              aria-label="Cerrar"
            >
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Nombre *">
              <Input
                value={form.name}
                onChange={(e) => setField("name", e.target.value)}
                placeholder="p. ej. Fondo Buyout Europe III"
              />
            </Field>
            <Field label="Tipo">
              <NativeSelect
                value={form.type}
                onChange={(v) => setField("type", v as AltInvestmentType)}
                options={TYPE_OPTIONS}
              />
            </Field>
            <Field label="Estado">
              <NativeSelect
                value={form.status ?? "ACTIVE"}
                onChange={(v) => setField("status", v as "ACTIVE" | "REALIZED")}
                options={[
                  ["ACTIVE", "Activa"],
                  ["REALIZED", "Realizada"],
                ]}
              />
            </Field>
            <Field label="Gestora / Banco">
              <Input
                value={form.manager ?? ""}
                onChange={(e) => setField("manager", e.target.value)}
                placeholder="p. ej. Banca privada X"
              />
            </Field>
            <Field label="ISIN">
              <Input
                value={form.isin ?? ""}
                onChange={(e) =>
                  setField("isin", e.target.value.toUpperCase().slice(0, 12) || null)
                }
                placeholder="ES0000000000"
                className="font-mono"
              />
            </Field>
            <Field label="Año (vintage)">
              <Input
                type="number"
                value={form.vintage_year ?? ""}
                onChange={(e) =>
                  setField(
                    "vintage_year",
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                placeholder="2023"
              />
            </Field>
            <Field label="Geografía">
              <Input
                value={form.geography ?? ""}
                onChange={(e) => setField("geography", e.target.value)}
                placeholder="Europa, EE.UU., Global…"
              />
            </Field>
            <Field label="Divisa">
              <Input
                value={form.currency ?? "EUR"}
                onChange={(e) =>
                  setField("currency", e.target.value.toUpperCase().slice(0, 3))
                }
                placeholder="EUR"
              />
            </Field>
            <Field label="Capital comprometido">
              <NumberInput
                value={form.committed_capital ?? 0}
                onChange={(v) => setField("committed_capital", v)}
              />
            </Field>
            <Field label="Capital desembolsado (called)">
              <NumberInput
                value={form.called_capital ?? 0}
                onChange={(v) => setField("called_capital", v)}
              />
            </Field>
            <Field label="Distribuido">
              <NumberInput
                value={form.distributed_capital ?? 0}
                onChange={(v) => setField("distributed_capital", v)}
              />
            </Field>
            <Field label="NAV actual">
              <NumberInput
                value={form.current_nav ?? 0}
                onChange={(v) => setField("current_nav", v)}
              />
            </Field>
            <Field label="Notas">
              <Input
                value={form.notes ?? ""}
                onChange={(e) => setField("notes", e.target.value)}
                placeholder="Opcional"
              />
            </Field>
            <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3">
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Guardando…" : "Guardar"}
              </Button>
              <Button variant="outline" onClick={() => setFormOpen(false)}>
                Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Positions table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Posiciones</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-40" />
          ) : items.length === 0 ? (
            <div className="py-10 text-center text-muted-foreground">
              <Landmark className="mx-auto mb-3 h-10 w-10 opacity-40" />
              <p>No hay inversiones alternativas todavía.</p>
              <Button variant="outline" size="sm" className="mt-4" onClick={openCreate}>
                <Plus className="mr-2 h-4 w-4" /> Añadir la primera
              </Button>
            </div>
          ) : (
            <>
              {/* Mobile */}
              <div className="divide-y sm:hidden">
                {items.map((inv) => (
                  <div key={inv.id} className="flex flex-col gap-2 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-medium">{inv.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {[inv.manager, inv.vintage_year, inv.geography]
                            .filter(Boolean)
                            .join(" · ")}
                        </div>
                        <div className="mt-1 flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[10px]">
                            {TYPE_LABELS[inv.type]}
                          </Badge>
                          {inv.status === "REALIZED" && (
                            <Badge variant="secondary" className="text-[10px]">
                              Realizada
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => openEdit(inv)}
                          aria-label="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(inv)}
                          aria-label="Eliminar"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <p className="text-xs text-muted-foreground">Comprometido</p>
                        <p className="tabular-nums">{formatEur(inv.committed_capital)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Called</p>
                        <p className="tabular-nums">{formatEur(inv.called_capital)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">NAV</p>
                        <p className="tabular-nums">{formatEur(inv.current_nav)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">TVPI / DPI</p>
                        <p className="tabular-nums">
                          {fmtMultiple(inv.tvpi)} / {fmtMultiple(inv.dpi)}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {/* Desktop */}
              <Table className="hidden sm:table">
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead className="text-right">Comprometido</TableHead>
                    <TableHead className="text-right">Called</TableHead>
                    <TableHead className="text-right">NAV</TableHead>
                    <TableHead className="text-right">TVPI</TableHead>
                    <TableHead className="text-right">DPI</TableHead>
                    <TableHead className="w-[90px]" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((inv) => (
                    <TableRow key={inv.id}>
                      <TableCell>
                        <div className="font-medium">{inv.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {[inv.manager, inv.vintage_year, inv.geography]
                            .filter(Boolean)
                            .join(" · ")}
                          {inv.status === "REALIZED" && (
                            <Badge variant="secondary" className="ml-2 text-[10px]">
                              Realizada
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{TYPE_LABELS[inv.type]}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatEur(inv.committed_capital)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatEur(inv.called_capital)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {formatEur(inv.current_nav)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtMultiple(inv.tvpi)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtMultiple(inv.dpi)}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEdit(inv)}
                            aria-label="Editar"
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDelete(inv)}
                            aria-label="Eliminar"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          {icon}
          {label}
        </div>
        <div className="mt-2 text-2xl font-bold tabular-nums">{value}</div>
        {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}

function NativeSelect({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {options.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  );
}

function NumberInput({
  value,
  onChange,
}: {
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <Input
      type="number"
      step="0.01"
      value={value}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : 0)}
    />
  );
}
