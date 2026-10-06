"use client";

import React, { useEffect, useState, useCallback } from "react";
import { portfolioApi, tradesApi } from "@/lib/api";
import type { PortfolioSnapshot, PositionRecord, OrderRecord, HoldingRecord } from "@/lib/types";
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
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui";
import {
  Wallet,
  TrendingUp,
  RefreshCw,
  Coins,
  ShieldAlert,
  ArrowUpRight,
  Clock,
  CheckCircle2,
  XCircle,
  Briefcase,
  Layers,
} from "lucide-react";

export default function PortfolioPage() {
  const [snapshot, setSnapshot] = useState<PortfolioSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("positions");

  const fetchPortfolio = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const data = await portfolioApi.getSnapshot();
      setSnapshot(data);
    } catch {
      // Non-fatal fallback
    } finally {
      setLoading(false);
      if (isManual) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchPortfolio();
    const interval = setInterval(() => fetchPortfolio(), 10000);
    return () => clearInterval(interval);
  }, [fetchPortfolio]);

  // Derived data
  const positions: PositionRecord[] = Array.isArray(snapshot?.positions) ? snapshot.positions : [];
  const holdings: HoldingRecord[] = Array.isArray(snapshot?.holdings) ? snapshot.holdings : [];
  const orders: OrderRecord[] = Array.isArray(snapshot?.open_orders) ? snapshot.open_orders : [];

  const totalUnrealizedPnl = positions.reduce(
    (acc, pos) => acc + (pos.unrealized_pnl ?? 0),
    0
  );
  const totalRealizedPnl = snapshot?.day_pnl ?? 0.0;
  const availableMargin = snapshot?.cash ?? 1000000.0;
  const totalPortfolioValue = snapshot?.total_value ?? (availableMargin + totalUnrealizedPnl);
  const dayPnlPct = snapshot?.day_pnl_pct ?? 0.0;

  return (
    <div className="space-y-6">
      {/* Header with Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2">
            <Briefcase className="h-5 w-5 text-blue-400" />
            <span>Portfolio & Open Positions</span>
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Capital allocation, intraday active positions, delivery holdings, and order audit
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" size="sm">
            AUTO-SYNC 10S
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={() => fetchPortfolio(true)}
            loading={refreshing}
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
          >
            Refresh
          </Button>
        </div>
      </div>

      {/* 4 Required Capital Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Portfolio Value"
          value={formatINR(totalPortfolioValue)}
          change={dayPnlPct}
          changeLabel="today"
          icon={<Wallet className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Available Margin"
          value={formatINR(availableMargin)}
          subtitle="Ready cash balance"
          icon={<Coins className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Realized P&L"
          value={formatINR(totalRealizedPnl)}
          isPositive={totalRealizedPnl >= 0}
          subtitle="Booked intraday profit"
          icon={<TrendingUp className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Unrealized P&L"
          value={formatINR(totalUnrealizedPnl)}
          isPositive={totalUnrealizedPnl >= 0}
          subtitle={`${positions.length} open active positions`}
          icon={<Layers className="h-4 w-4" />}
          loading={loading}
        />
      </div>

      {/* Tabs Navigation for Positions, Holdings, and Orders */}
      <Tabs defaultValue="positions">
        <TabsList>
          <TabsTrigger value="positions">
            Open Positions ({positions.length})
          </TabsTrigger>
          <TabsTrigger value="holdings">
            Holdings & CNC ({holdings.length})
          </TabsTrigger>
          <TabsTrigger value="orders">
            Today&apos;s Orders ({orders.length})
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Open Positions */}
        <TabsContent value="positions">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Intraday Open Positions</CardTitle>
                <p className="text-xs text-gray-400 mt-0.5">
                  Live mark-to-market prices, risk stops, and target projections
                </p>
              </div>
              <Badge variant="success" size="sm" dot>
                {positions.length} ACTIVE
              </Badge>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Avg Entry</TableHead>
                    <TableHead className="text-right">LTP</TableHead>
                    <TableHead className="text-right">Current Value</TableHead>
                    <TableHead className="text-right">Unrealized P&L</TableHead>
                    <TableHead className="text-center">Stop Loss</TableHead>
                    <TableHead className="text-center">Target</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.length > 0 ? (
                    positions.map((pos) => {
                    const isProfit = (pos.unrealized_pnl ?? 0) >= 0;
                    const currentValue =
                      pos.current_value ?? (pos.quantity * (pos.ltp ?? pos.avg_price));
                    return (
                      <TableRow key={pos.symbol}>
                        <TableCell>
                          <div className="font-semibold text-white">{pos.symbol}</div>
                          {pos.sector && (
                            <span className="text-[10px] text-gray-400">{pos.sector}</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={pos.side === "BUY" ? "success" : "danger"}
                            size="sm"
                          >
                            {pos.side}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          {pos.quantity}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatINR(pos.avg_price)}
                        </TableCell>
                        <TableCell className="text-right font-mono font-semibold text-gray-100">
                          {formatINR(pos.ltp ?? pos.avg_price)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-gray-300">
                          {formatINR(currentValue)}
                        </TableCell>
                        <TableCell className="text-right font-mono font-semibold">
                          <span className={isProfit ? "text-emerald-400" : "text-rose-400"}>
                            {formatINR(pos.unrealized_pnl)} ({formatPct(pos.unrealized_pnl_pct)})
                          </span>
                        </TableCell>
                        <TableCell className="text-center font-mono text-rose-400 text-xs">
                          {pos.stop_loss ? formatINR(pos.stop_loss) : "-"}
                        </TableCell>
                        <TableCell className="text-center font-mono text-emerald-400 text-xs">
                          {pos.target ? formatINR(pos.target) : "-"}
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-8 text-gray-500">
                      No open positions. Active trades will appear here once executed.
                    </TableCell>
                  </TableRow>
                )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Holdings (CNC) */}
        <TabsContent value="holdings">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Long-Term Equity Holdings (CNC)</CardTitle>
                <p className="text-xs text-gray-400 mt-0.5">
                  Delivery portfolio assets and overall capital appreciation
                </p>
              </div>
              <Badge variant="outline" size="sm">
                {holdings.length} Assets
              </Badge>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Sector</TableHead>
                    <TableHead className="text-right">Quantity</TableHead>
                    <TableHead className="text-right">Avg Cost</TableHead>
                    <TableHead className="text-right">Current Price</TableHead>
                    <TableHead className="text-right">Holding Value</TableHead>
                    <TableHead className="text-right">Total P&L</TableHead>
                    <TableHead className="text-right">Day Change</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {holdings.length > 0 ? (
                    holdings.map((h) => {
                    const isProfit = h.total_pnl >= 0;
                    const isDayUp = h.day_change_pct >= 0;
                    return (
                      <TableRow key={h.symbol}>
                        <TableCell className="font-semibold text-white">
                          {h.symbol}
                        </TableCell>
                        <TableCell className="text-xs text-gray-400">
                          {h.sector || "Equity"}
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          {h.quantity}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatINR(h.avg_price)}
                        </TableCell>
                        <TableCell className="text-right font-mono font-semibold text-gray-100">
                          {formatINR(h.current_price)}
                        </TableCell>
                        <TableCell className="text-right font-mono text-gray-200">
                          {formatINR(h.current_value)}
                        </TableCell>
                        <TableCell className="text-right font-mono font-semibold">
                          <span className={isProfit ? "text-emerald-400" : "text-rose-400"}>
                            {formatINR(h.total_pnl)} ({formatPct(h.total_pnl_pct)})
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          <span className={isDayUp ? "text-emerald-400" : "text-rose-400"}>
                            {formatPct(h.day_change_pct)}
                          </span>
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-8 text-gray-500">
                      No delivery holdings in account.
                    </TableCell>
                  </TableRow>
                )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Today's Orders */}
        <TabsContent value="orders">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle>Today&apos;s Order Ledger</CardTitle>
                <p className="text-xs text-gray-400 mt-0.5">
                  Intraday trade orders submitted to the broker / paper execution bridge
                </p>
              </div>
              <Badge variant="outline" size="sm">
                {orders.length} Executions
              </Badge>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Order ID</TableHead>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Side</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Qty</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                    <TableHead>Trigger Source</TableHead>
                    <TableHead className="text-center">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.length > 0 ? (
                    orders.map((ord) => {
                    const isFilled = ord.status === "FILLED" || ord.status === "COMPLETE";
                    const isPending = ord.status === "PENDING";
                    const isRejected = ord.status === "REJECTED" || ord.status === "CANCELLED";

                    return (
                      <TableRow key={ord.order_id}>
                        <TableCell className="text-xs text-gray-400 font-mono">
                          {formatDateIST(ord.created_at, {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </TableCell>
                        <TableCell className="font-mono text-xs text-blue-300">
                          {ord.order_id}
                        </TableCell>
                        <TableCell className="font-semibold text-white">
                          {ord.symbol}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={ord.side === "BUY" ? "success" : "danger"}
                            size="sm"
                          >
                            {ord.side}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-xs text-gray-400 font-mono">
                          {ord.order_type}
                        </TableCell>
                        <TableCell className="text-right font-mono font-medium">
                          {ord.quantity}
                        </TableCell>
                        <TableCell className="text-right font-mono">
                          {formatINR(ord.price)}
                        </TableCell>
                        <TableCell className="text-xs text-gray-300 max-w-xs truncate">
                          {ord.trigger_source || "Algorithmic"}
                          {ord.rejection_reason && (
                            <span className="block text-[10px] text-rose-400">
                              Reason: {ord.rejection_reason}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge
                            variant={
                              isFilled
                                ? "success"
                                : isPending
                                ? "warning"
                                : "danger"
                            }
                            size="sm"
                            dot={isPending}
                          >
                            {ord.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })
                ) : (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-8 text-gray-500">
                      No orders placed today.
                    </TableCell>
                  </TableRow>
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
