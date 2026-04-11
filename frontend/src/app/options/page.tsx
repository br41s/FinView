"use client";

import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bell,
  Eye,
  Play,
  Square,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Zap,
} from "lucide-react";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// ── Types ───────────────────────────────────────────────────────────

interface Snapshot {
  id: number;
  timestamp: string;
  ticker: string;
  current_price: string | number;
  call_volume: number;
  put_volume: number;
  put_call_ratio_volume: string | number | null;
  avg_call_iv: string | number | null;
  avg_put_iv: string | number | null;
  historical_volatility: string | number | null;
  iv_skew: string | number | null;
  market_sentiment: string | null;
}

interface Alert {
  id: number;
  timestamp: string;
  ticker: string;
  alert_type: string;
  message: string;
  severity: string;
  acknowledged: boolean;
}

interface Unusual {
  id: number;
  timestamp: string;
  ticker: string;
  option_type: string;
  strike: string | number;
  expiration: string;
  volume: number;
  open_interest: number;
  vol_oi_ratio: string | number;
  implied_volatility: string | number | null;
  last_price: string | number | null;
}

interface AgentStatus {
  running: boolean;
  interval_minutes: number;
  last_cycle: string | null;
  total_cycles: number;
}

interface WatchlistItem {
  id: number;
  ticker: string;
  name: string;
  enabled: boolean;
  created_at: string;
}

// ── Helpers ─────────────────────────────────────────────────────────

function fmt(n: number | string | null | undefined, d = 2): string {
  if (n == null) return "—";
  const v = typeof n === "string" ? parseFloat(n) : n;
  if (isNaN(v)) return "—";
  return v.toLocaleString("es-ES", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

function severityColor(s: string) {
  switch (s) {
    case "HIGH":
      return "destructive";
    case "MEDIUM":
      return "secondary";
    default:
      return "outline";
  }
}

function sentimentIcon(s: string | null) {
  if (!s) return null;
  if (s.includes("BULLISH"))
    return <TrendingUp className="h-4 w-4 text-green-500" />;
  if (s.includes("BEARISH"))
    return <TrendingDown className="h-4 w-4 text-red-500" />;
  return <Activity className="h-4 w-4 text-muted-foreground" />;
}

// ── Component ───────────────────────────────────────────────────────

export default function OptionsPage() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [unusual, setUnusual] = useState<Unusual[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [newTicker, setNewTicker] = useState("");

  async function loadData() {
    try {
      const [snaps, alts, unu, wl, status] = await Promise.all([
        api.options.snapshots() as Promise<Snapshot[]>,
        api.options.alerts() as Promise<Alert[]>,
        api.options.unusual() as Promise<Unusual[]>,
        api.options.watchlist() as Promise<WatchlistItem[]>,
        api.options.agentStatus() as Promise<AgentStatus>,
      ]);
      setSnapshots(snaps);
      setAlerts(alts);
      setUnusual(unu);
      setWatchlist(wl);
      setAgentStatus(status);
    } catch (e) {
      console.error("Failed to load options data:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleRunCycle() {
    setRunning(true);
    try {
      await api.options.runCycle();
      await loadData();
    } finally {
      setRunning(false);
    }
  }

  async function handleToggleAgent() {
    if (agentStatus?.running) {
      await api.options.stopAgent();
    } else {
      await api.options.startAgent();
    }
    const status = (await api.options.agentStatus()) as AgentStatus;
    setAgentStatus(status);
  }

  async function handleAddTicker() {
    if (!newTicker.trim()) return;
    await api.options.addToWatchlist(newTicker.trim().toUpperCase());
    setNewTicker("");
    const wl = (await api.options.watchlist()) as WatchlistItem[];
    setWatchlist(wl);
  }

  async function handleRemoveTicker(id: number) {
    await api.options.removeFromWatchlist(id);
    setWatchlist((prev) => prev.filter((w) => w.id !== id));
  }

  async function handleAckAlert(id: number) {
    await api.options.ackAlert(id);
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, acknowledged: true } : a)),
    );
  }

  async function handleAckAll() {
    await api.options.ackAllAlerts();
    setAlerts((prev) => prev.map((a) => ({ ...a, acknowledged: true })));
  }

  // Group latest snapshot per ticker
  const latestByTicker = new Map<string, Snapshot>();
  for (const s of snapshots) {
    if (!latestByTicker.has(s.ticker)) {
      latestByTicker.set(s.ticker, s);
    }
  }

  const unreadAlerts = alerts.filter((a) => !a.acknowledged);

  if (loading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Options Monitor</h1>
          <p className="text-muted-foreground">
            Real-time options chain analysis, Greeks &amp; smart money detection
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRunCycle}
            disabled={running}
          >
            {running ? (
              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Run Cycle
          </Button>
          <Button
            variant={agentStatus?.running ? "destructive" : "default"}
            size="sm"
            onClick={handleToggleAgent}
          >
            {agentStatus?.running ? (
              <>
                <Square className="mr-2 h-4 w-4" /> Stop
              </>
            ) : (
              <>
                <Play className="mr-2 h-4 w-4" /> Auto
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Watchlist</CardTitle>
            <Eye className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{watchlist.length}</div>
            <p className="text-xs text-muted-foreground">
              {watchlist.filter((w) => w.enabled).length} active
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Cycles</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {agentStatus?.total_cycles ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              {agentStatus?.last_cycle
                ? `Last: ${new Date(agentStatus.last_cycle).toLocaleString("es-ES")}`
                : "No cycles yet"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Alerts</CardTitle>
            <Bell className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{unreadAlerts.length}</div>
            <p className="text-xs text-muted-foreground">
              {alerts.length} total (7d)
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Smart Money</CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{unusual.length}</div>
            <p className="text-xs text-muted-foreground">
              Unusual activity (7d)
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="dashboard">
        <TabsList>
          <TabsTrigger value="dashboard">
            <BarChart3 className="mr-1 h-4 w-4" /> Dashboard
          </TabsTrigger>
          <TabsTrigger value="watchlist">
            <Eye className="mr-1 h-4 w-4" /> Watchlist
          </TabsTrigger>
          <TabsTrigger value="alerts">
            <Bell className="mr-1 h-4 w-4" /> Alerts
            {unreadAlerts.length > 0 && (
              <Badge
                variant="destructive"
                className="ml-1 px-1.5 py-0.5 text-xs"
              >
                {unreadAlerts.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="unusual">
            <Zap className="mr-1 h-4 w-4" /> Smart Money
          </TabsTrigger>
        </TabsList>

        {/* ── Dashboard Tab ── */}
        <TabsContent value="dashboard" className="space-y-4">
          {latestByTicker.size === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-muted-foreground">
                No snapshots yet. Add tickers to your watchlist and run a cycle.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from(latestByTicker.values()).map((snap) => (
                <Card key={snap.ticker}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-lg">{snap.ticker}</CardTitle>
                      <div className="flex items-center gap-1">
                        {sentimentIcon(snap.market_sentiment)}
                        <span className="text-xs">{snap.market_sentiment}</span>
                      </div>
                    </div>
                    <CardDescription>
                      ${fmt(snap.current_price)} •{" "}
                      {new Date(snap.timestamp).toLocaleString("es-ES")}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-muted-foreground">Call Vol</span>
                        <p className="font-medium">
                          {snap.call_volume.toLocaleString()}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Put Vol</span>
                        <p className="font-medium">
                          {snap.put_volume.toLocaleString()}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">P/C Ratio</span>
                        <p className="font-medium">
                          {fmt(snap.put_call_ratio_volume)}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">IV Skew</span>
                        <p className="font-medium">{fmt(snap.iv_skew, 1)}%</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Call IV</span>
                        <p className="font-medium">
                          {fmt(snap.avg_call_iv, 1)}%
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Put IV</span>
                        <p className="font-medium">
                          {fmt(snap.avg_put_iv, 1)}%
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Watchlist Tab ── */}
        <TabsContent value="watchlist" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Manage Watchlist</CardTitle>
              <CardDescription>
                Add tickers to monitor for options activity
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <input
                  className="flex h-9 w-full max-w-xs rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  placeholder="Ticker (e.g. AAPL, ACX.MC)"
                  value={newTicker}
                  onChange={(e) => setNewTicker(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddTicker()}
                />
                <Button size="sm" onClick={handleAddTicker}>
                  Add
                </Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticker</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Added</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {watchlist.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={5}
                        className="text-center text-muted-foreground"
                      >
                        No tickers in watchlist
                      </TableCell>
                    </TableRow>
                  ) : (
                    watchlist.map((w) => (
                      <TableRow key={w.id}>
                        <TableCell className="font-medium">
                          {w.ticker}
                        </TableCell>
                        <TableCell>{w.name || "—"}</TableCell>
                        <TableCell>
                          <Badge variant={w.enabled ? "default" : "secondary"}>
                            {w.enabled ? "Active" : "Paused"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {new Date(w.created_at).toLocaleDateString("es-ES")}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              api.options
                                .toggleWatchlistItem(w.id)
                                .then(() =>
                                  setWatchlist((prev) =>
                                    prev.map((item) =>
                                      item.id === w.id
                                        ? { ...item, enabled: !item.enabled }
                                        : item,
                                    ),
                                  ),
                                )
                            }
                          >
                            {w.enabled ? "Pause" : "Enable"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive"
                            onClick={() => handleRemoveTicker(w.id)}
                          >
                            Remove
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Alerts Tab ── */}
        <TabsContent value="alerts" className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">Recent Alerts</h3>
            {unreadAlerts.length > 0 && (
              <Button variant="outline" size="sm" onClick={handleAckAll}>
                Mark all read
              </Button>
            )}
          </div>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Ticker</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Message</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alerts.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={6}
                        className="text-center text-muted-foreground"
                      >
                        No alerts yet
                      </TableCell>
                    </TableRow>
                  ) : (
                    alerts.map((a) => (
                      <TableRow
                        key={a.id}
                        className={a.acknowledged ? "opacity-50" : ""}
                      >
                        <TableCell className="text-xs">
                          {new Date(a.timestamp).toLocaleString("es-ES")}
                        </TableCell>
                        <TableCell className="font-medium">
                          {a.ticker}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{a.alert_type}</Badge>
                        </TableCell>
                        <TableCell>{a.message}</TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              severityColor(a.severity) as
                                | "destructive"
                                | "secondary"
                                | "outline"
                            }
                          >
                            {a.severity}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {!a.acknowledged && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleAckAlert(a.id)}
                            >
                              Ack
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Smart Money Tab ── */}
        <TabsContent value="unusual" className="space-y-4">
          <h3 className="text-lg font-semibold">Unusual Activity</h3>
          <Card>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Ticker</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Strike</TableHead>
                    <TableHead>Exp</TableHead>
                    <TableHead>Volume</TableHead>
                    <TableHead>OI</TableHead>
                    <TableHead>Vol/OI</TableHead>
                    <TableHead>IV</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {unusual.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={9}
                        className="text-center text-muted-foreground"
                      >
                        No unusual activity detected
                      </TableCell>
                    </TableRow>
                  ) : (
                    unusual.map((u) => (
                      <TableRow key={u.id}>
                        <TableCell className="text-xs">
                          {new Date(u.timestamp).toLocaleString("es-ES")}
                        </TableCell>
                        <TableCell className="font-medium">
                          {u.ticker}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              u.option_type === "CALL" ? "default" : "secondary"
                            }
                          >
                            {u.option_type}
                          </Badge>
                        </TableCell>
                        <TableCell>${fmt(u.strike)}</TableCell>
                        <TableCell>{u.expiration}</TableCell>
                        <TableCell>{u.volume.toLocaleString()}</TableCell>
                        <TableCell>
                          {u.open_interest.toLocaleString()}
                        </TableCell>
                        <TableCell className="font-medium text-amber-600">
                          {fmt(u.vol_oi_ratio, 1)}x
                        </TableCell>
                        <TableCell>
                          {u.implied_volatility
                            ? `${fmt(Number(u.implied_volatility) * 100, 1)}%`
                            : "—"}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
