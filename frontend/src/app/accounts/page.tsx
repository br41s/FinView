"use client";

import { useEffect, useState, Suspense } from "react";
import { Plus, Trash2, Pencil, Building2 } from "lucide-react";

import { api } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
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
import { LoadingDots } from "@/components/loading-dots";
import { QuickNav } from "@/components/QuickNav";
import { HeaderActions } from "@/components/HeaderActions";
import { usePrivacyToggle } from "@/hooks/use-privacy-toggle";

const BROKERS = ["BBVA", "DEGIRO", "ETORO", "IBKR", "ING", "TR"];
const CURRENCIES = ["EUR", "USD", "GBP", "CHF"];

interface AccountItem {
  id: number;
  broker: string;
  account_id: string;
  name: string;
  currency: string;
  transaction_count: number;
  import_count: number;
}

function AccountsContent() {
  const { privacy, togglePrivacy } = usePrivacyToggle();
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  // Form state
  const [broker, setBroker] = useState("IBKR");
  const [accountId, setAccountId] = useState("");
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function loadAccounts() {
    try {
      const data = (await api.accounts.list()) as AccountItem[];
      setAccounts(data);
    } catch (e) {
      console.error("Failed to load accounts:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAccounts();
  }, []);

  function resetForm() {
    setBroker("IBKR");
    setAccountId("");
    setName("");
    setCurrency("EUR");
    setShowForm(false);
    setEditingId(null);
    setError("");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");

    try {
      if (editingId) {
        await api.accounts.update(editingId, { name, currency });
      } else {
        await api.accounts.create({
          broker,
          account_id: accountId,
          name,
          currency,
        });
      }
      resetForm();
      await loadAccounts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido");
    } finally {
      setSaving(false);
    }
  }

  function startEdit(acct: AccountItem) {
    setEditingId(acct.id);
    setBroker(acct.broker);
    setAccountId(acct.account_id);
    setName(acct.name);
    setCurrency(acct.currency);
    setShowForm(true);
  }

  async function handleDelete(acct: AccountItem) {
    const label = acct.name || `${acct.broker} ${acct.account_id}`;
    const hasData = acct.transaction_count > 0 || acct.import_count > 0;
    const confirmed = window.confirm(
      hasData
        ? `¿Eliminar "${label}" y sus ${acct.transaction_count} transacciones e importaciones? Esta acción no se puede deshacer.`
        : `¿Eliminar la cuenta "${label}"?`,
    );
    if (!confirmed) return;
    try {
      await api.accounts.delete(acct.id);
      setAccounts((prev) => prev.filter((a) => a.id !== acct.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al eliminar");
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <LoadingDots text="Cargando cuentas" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <Building2 className="h-6 w-6" />
            Cuentas
          </h1>
          <p className="text-muted-foreground">
            Gestiona tus cuentas de broker
          </p>
        </div>
        <div className="flex items-center gap-3">
          <HeaderActions privacy={privacy} onTogglePrivacy={togglePrivacy} />
          <QuickNav current="/portfolio" />
          {!showForm && (
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Nueva cuenta
            </Button>
          )}
        </div>
      </div>

      {/* Create/Edit Form */}
      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>
              {editingId ? "Editar cuenta" : "Nueva cuenta"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="broker">Broker</Label>
                  <select
                    id="broker"
                    aria-label="Broker"
                    value={broker}
                    onChange={(e) => setBroker(e.target.value)}
                    disabled={!!editingId}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  >
                    {BROKERS.map((b) => (
                      <option key={b} value={b}>
                        {b}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="account_id">ID de cuenta</Label>
                  <Input
                    id="account_id"
                    value={accountId}
                    onChange={(e) => setAccountId(e.target.value)}
                    placeholder="U12345678"
                    disabled={!!editingId}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="name">Nombre (opcional)</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="Mi cuenta principal"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="currency">Moneda</Label>
                  <select
                    id="currency"
                    aria-label="Moneda"
                    value={currency}
                    onChange={(e) => setCurrency(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {CURRENCIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {error && <p className="text-sm text-red-600">{error}</p>}

              <div className="flex gap-2">
                <Button type="submit" disabled={saving}>
                  {saving
                    ? "Guardando..."
                    : editingId
                      ? "Actualizar"
                      : "Crear cuenta"}
                </Button>
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Accounts List */}
      {accounts.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Building2 className="h-12 w-12 text-muted-foreground mb-4" />
            <CardTitle className="mb-2">Sin cuentas</CardTitle>
            <CardDescription>
              Crea tu primera cuenta de broker o importa datos desde el
              dashboard.
            </CardDescription>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Tus cuentas ({accounts.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {/* Mobile */}
            <div className="divide-y sm:hidden">
              {accounts.map((acct) => (
                <div key={acct.id} className="flex items-start justify-between gap-2 p-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{acct.broker}</Badge>
                      <span className="font-mono text-sm text-muted-foreground">
                        {acct.account_id}
                      </span>
                    </div>
                    <p className="mt-1 text-sm">{acct.name || "—"}</p>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-muted-foreground">
                      <span>{acct.currency}</span>
                      <span>{acct.transaction_count} transacciones</span>
                      <span>{acct.import_count} imports</span>
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="icon" onClick={() => startEdit(acct)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDelete(acct)}
                      title="Eliminar cuenta"
                      className="text-destructive hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            {/* Desktop */}
            <Table className="hidden sm:table">
              <TableHeader>
                <TableRow>
                  <TableHead>Broker</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Nombre</TableHead>
                  <TableHead className="text-center">Moneda</TableHead>
                  <TableHead className="text-right">Transacciones</TableHead>
                  <TableHead className="text-right">Imports</TableHead>
                  <TableHead className="text-right">Acciones</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {accounts.map((acct) => (
                  <TableRow key={acct.id}>
                    <TableCell>
                      <Badge variant="outline">{acct.broker}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      {acct.account_id}
                    </TableCell>
                    <TableCell>{acct.name || "—"}</TableCell>
                    <TableCell className="text-center">
                      {acct.currency}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {acct.transaction_count}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {acct.import_count}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => startEdit(acct)}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(acct)}
                          title="Eliminar cuenta"
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function AccountsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6">
          <Skeleton className="h-8 w-48" />
        </div>
      }
    >
      <AccountsContent />
    </Suspense>
  );
}
