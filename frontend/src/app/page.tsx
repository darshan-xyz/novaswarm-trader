"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { systemApi, portfolioApi, tradesApi } from "@/lib/api";
import type { SystemStatus, PortfolioSnapshot, TradeSummaryStats } from "@/lib/types";
import { formatINR, formatPct, formatDateIST } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  StatCard,
  Badge,
  Button,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui";
import {
  Server,
  Database,
  Cpu,
  Wallet,
  TrendingUp,
  RefreshCw,
  ScanSearch,
  MessageSquareCode,
  ShieldCheck,
  ArrowUpRight,
  Award,
  Zap,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

export default function SystemOverviewPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioSnapshot | null>(null);
  const [tradeStats, setTradeStats] = useState<TradeSummaryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const loadData = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const [statusRes, portRes, statsRes] = await Promise.allSettled([
        systemApi.getStatus(),
        portfolioApi.getSnapshot(),
        tradesApi.getSummaryStats(),
      ]);

      if (statusRes.status === "fulfilled") {
        setStatus(statusRes.value);
      }
      if (portRes.status === "fulfilled") {
        setPortfolio(portRes.value);
      }
      if (statsRes.status === "fulfilled") {
        setTradeStats(statsRes.value);
      }
      setLastUpdated(new Date().toISOString());
    } catch {
      // Non-fatal, graceful UI degradation
    } finally {
      setLoading(false);
      if (isManual) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(() => loadData(), 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  const activeLlms =
    status?.services?.llms && typeof status.services.llms === "object"
      ? Object.entries(status.services.llms)
          .filter(([, v]) => Boolean(v))
          .map(([k]) => k)
      : [];

  // Realized today or overall P&L
  const todayRealizedPnl = tradeStats?.total_realized_pnl ?? 0.0;
  const winRateValue = tradeStats?.win_rate
    ? tradeStats.win_rate * 100
    : 0.0;

  const positionsList =
    Array.isArray(portfolio?.positions) ? portfolio.positions : [];

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2">
            <span>System Overview Cockpit</span>
            <Badge variant="info" size="sm" className="hidden sm:inline-flex">
              v{status?.version || "0.1.0"}
            </Badge>
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Live infrastructure connectivity, risk shields, and portfolio KPIs
            {lastUpdated && ` • Updated: ${formatDateIST(lastUpdated, { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`}
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <Badge
            variant={status?.mode === "live" ? "danger" : "warning"}
            size="md"
            dot
          >
            {status?.mode ? status.mode.toUpperCase() : "PAPER"} TRADING
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadData(true)}
            loading={refreshing}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
          >
            Refresh Status
          </Button>
        </div>
      </div>

      {/* 5-Card Portfolio KPI Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
        <StatCard
          title="Total Equity"
          value={formatINR(portfolio?.total_value ?? (portfolio?.cash ?? 1000000))}
          change={portfolio?.day_pnl_pct ?? 0.0}
          changeLabel="today"
          icon={<Wallet className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Cash Balance"
          value={formatINR(portfolio?.cash ?? 1000000)}
          subtitle="Available margin"
          loading={loading}
        />
        <StatCard
          title="Today's Realized P&L"
          value={formatINR(todayRealizedPnl)}
          isPositive={todayRealizedPnl >= 0}
          icon={<TrendingUp className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Active Positions"
          value={positionsList.length}
          subtitle={formatINR(portfolio?.positions_value ?? 0)}
          icon={<Zap className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Win Rate"
          value={`${winRateValue.toFixed(1)}%`}
          subtitle={`${tradeStats?.winning_trades ?? 0}W / ${tradeStats?.losing_trades ?? 0}L`}
          icon={<Award className="h-4 w-4" />}
          loading={loading}
        />
      </div>

      {/* Infrastructure Health Status Grid */}
      <div>
        <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
          <Server className="h-4 w-4 text-blue-400" />
          Infrastructure Health Monitors
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Broker Card */}
          <Card className="p-4 bg-gray-900/80 hover:border-gray-700 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Broker Gateway</span>
              <Badge
                variant={status?.broker?.token_valid ? "success" : "warning"}
                size="sm"
                dot
              >
                {status?.broker?.token_valid ? "CONNECTED" : "ACTIVE (PAPER)"}
              </Badge>
            </div>
            <div className="mt-2 text-base font-semibold text-white flex items-center gap-1.5">
              <span>{status?.broker?.name || "INDstocks Broker"}</span>
            </div>
            <p className="mt-1 text-[11px] text-gray-400">
              {status?.broker?.token_remaining
                ? `Token expires in: ${status.broker.token_remaining}`
                : "Active paper execution engine (₹10L virtual capital)"}
            </p>
          </Card>

          {/* Supabase DB Card */}
          <Card className="p-4 bg-gray-900/80 hover:border-gray-700 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Database & Vector Store</span>
              <Badge
                variant={status?.services?.supabase ? "success" : "secondary"}
                size="sm"
                dot
              >
                {status?.services?.supabase ? "POSTGRES CONNECTED" : "LOCAL CACHE READY"}
              </Badge>
            </div>
            <div className="mt-2 text-base font-semibold text-white flex items-center gap-1.5">
              <Database className="h-4 w-4 text-emerald-400" />
              <span>Supabase</span>
            </div>
            <p className="mt-1 text-[11px] text-gray-400">
              {status?.services?.supabase
                ? "Trade ledger, reflection logs & BM25 vectors connected"
                : "In-memory trade persistence active"}
            </p>
          </Card>

          {/* Redis Cache Card */}
          <Card className="p-4 bg-gray-900/80 hover:border-gray-700 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">High-Speed State Cache</span>
              <Badge
                variant={status?.services?.redis ? "success" : "secondary"}
                size="sm"
                dot
              >
                {status?.services?.redis ? "ONLINE" : "STANDBY"}
              </Badge>
            </div>
            <div className="mt-2 text-base font-semibold text-white flex items-center gap-1.5">
              <Zap className="h-4 w-4 text-amber-400" />
              <span>Upstash Redis</span>
            </div>
            <p className="mt-1 text-[11px] text-gray-400">
              {status?.services?.redis
                ? "Sub-millisecond lock sync & order deduplication"
                : "Local state locks & thread safety enabled"}
            </p>
          </Card>

          {/* LLM Swarm Card */}
          <Card className="p-4 bg-gray-900/80 hover:border-gray-700 transition-colors">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-400">Autonomous LLM Swarm</span>
              <Badge
                variant={activeLlms.length > 0 ? "success" : "warning"}
                size="sm"
                dot
              >
                {activeLlms.length > 0 ? `${activeLlms.length} PROVIDERS` : "READY"}
              </Badge>
            </div>
            <div className="mt-2 text-base font-semibold text-white flex items-center gap-1.5">
              <Cpu className="h-4 w-4 text-purple-400" />
              <span>Multi-Model Engine</span>
            </div>
            <p className="mt-1 text-[11px] text-gray-400">
              {activeLlms.length > 0
                ? `${activeLlms.map((m) => m.charAt(0).toUpperCase() + m.slice(1)).join(", ")} active`
                : "Configure LLM provider keys in .env"}
            </p>
          </Card>
        </div>
      </div>

      {/* Quick Launch & Open Positions Preview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Open Positions Summary */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Active Open Positions</CardTitle>
                <p className="text-xs text-gray-400 mt-0.5">Live intraday tracking with stop-loss & target</p>
              </div>
              <Link
                href="/portfolio"
                className="text-xs text-blue-400 hover:text-blue-300 font-medium inline-flex items-center gap-1"
              >
                View Full Portfolio <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Avg Entry</TableHead>
                    <TableHead className="text-right">LTP</TableHead>
                    <TableHead className="text-right">Unrealized P&L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positionsList.length > 0 ? (
                    positionsList.map((pos) => {
                    const isProfit = (pos.unrealized_pnl ?? 0) >= 0;
                    return (
                      <TableRow key={pos.symbol}>
                        <TableCell className="font-semibold text-white">{pos.symbol}</TableCell>
                        <TableCell>
                          <Badge
                            variant={pos.side === "BUY" ? "success" : "danger"}
                            size="sm"
                          >
                            {pos.side}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono">{pos.quantity}</TableCell>
                        <TableCell className="text-right font-mono">{formatINR(pos.avg_price)}</TableCell>
                        <TableCell className="text-right font-mono">
                          {formatINR(pos.ltp ?? pos.avg_price)}
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          <span className={isProfit ? "text-emerald-400" : "text-rose-400"}>
                            {formatINR(pos.unrealized_pnl)} ({formatPct(pos.unrealized_pnl_pct)})
                          </span>
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-6 text-xs text-gray-500">
                      No open positions. Active trades will appear here once executed.
                    </TableCell>
                  </TableRow>
                )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>

        {/* Quick Swarm Actions */}
        <div>
          <Card className="h-full flex flex-col justify-between">
            <CardHeader>
              <CardTitle>Trading Swarm Cockpit</CardTitle>
              <p className="text-xs text-gray-400 mt-0.5">Quick operational shortcuts</p>
            </CardHeader>
            <CardContent className="space-y-3 flex-1">
              <Link
                href="/scanner"
                className="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-950/60 hover:bg-gray-800/50 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-blue-900/30 text-blue-400 border border-blue-800/40">
                    <ScanSearch className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-blue-400">
                      Market Scanner Radar
                    </div>
                    <p className="text-[11px] text-gray-400">Detect breakouts & momentum setups</p>
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-gray-500 group-hover:text-blue-400" />
              </Link>

              <Link
                href="/analysis"
                className="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-950/60 hover:bg-gray-800/50 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-purple-900/30 text-purple-400 border border-purple-800/40">
                    <Cpu className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-purple-400">
                      Multi-Agent Swarm
                    </div>
                    <p className="text-[11px] text-gray-400">Launch real-time SSE analysis</p>
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-gray-500 group-hover:text-purple-400" />
              </Link>

              <Link
                href="/chat"
                className="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-950/60 hover:bg-gray-800/50 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-800/40">
                    <MessageSquareCode className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-emerald-400">
                      AI Trading Assistant
                    </div>
                    <p className="text-[11px] text-gray-400">Tool calls & conversational insights</p>
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-gray-500 group-hover:text-emerald-400" />
              </Link>

              <Link
                href="/settings"
                className="flex items-center justify-between p-3 rounded-lg border border-gray-800 bg-gray-950/60 hover:bg-gray-800/50 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded bg-amber-900/30 text-amber-400 border border-amber-800/40">
                    <ShieldCheck className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-white group-hover:text-amber-400">
                      Risk Simulator & DNA
                    </div>
                    <p className="text-[11px] text-gray-400">16 frozen rules & health logs</p>
                  </div>
                </div>
                <ArrowUpRight className="h-4 w-4 text-gray-500 group-hover:text-amber-400" />
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
