"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { tradesApi } from "@/lib/api";
import type { TradeRecord, TradeSummaryStats, TradeModelPrediction } from "@/lib/types";
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
  Modal,
  Select,
  Input,
  Spinner,
} from "@/components/ui";
import {
  History,
  Eye,
  RefreshCw,
  Filter,
  ArrowUpDown,
  TrendingUp,
  Award,
  Sparkles,
  BookOpen,
  Compass,
} from "lucide-react";

type SortField = "entry_time" | "symbol" | "side" | "quantity" | "realized_pnl";
type SortDirection = "asc" | "desc";


export default function TradesPage() {
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [stats, setStats] = useState<TradeSummaryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTrade, setSelectedTrade] = useState<TradeRecord | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sideFilter, setSideFilter] = useState<string>("all");
  const [searchSymbol, setSearchSymbol] = useState<string>("");

  // Sorting
  const [sortField, setSortField] = useState<SortField>("entry_time");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const loadTradesData = useCallback(async () => {
    setLoading(true);
    try {
      const [tradesRes, statsRes] = await Promise.allSettled([
        tradesApi.getTrades({
          status: statusFilter === "all" ? undefined : statusFilter,
          side: sideFilter === "all" ? undefined : sideFilter,
          symbol: searchSymbol.trim() || undefined,
        }),
        tradesApi.getSummaryStats(),
      ]);

      if (tradesRes.status === "fulfilled" && Array.isArray(tradesRes.value?.trades)) {
        setTrades(tradesRes.value.trades);
      } else {
        setTrades([]);
      }

      if (statsRes.status === "fulfilled" && statsRes.value) {
        setStats(statsRes.value);
      } else {
        setStats({
          total_trades: 0,
          winning_trades: 0,
          losing_trades: 0,
          win_rate: 0.0,
          total_realized_pnl: 0.0,
          gross_profit: 0.0,
          gross_loss: 0.0,
          profit_factor: 0.0,
        });
      }
    } catch {
      setTrades([]);
      setStats({
        total_trades: 0,
        winning_trades: 0,
        losing_trades: 0,
        win_rate: 0.0,
        total_realized_pnl: 0.0,
        gross_profit: 0.0,
        gross_loss: 0.0,
        profit_factor: 0.0,
      });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, sideFilter, searchSymbol]);

  useEffect(() => {
    loadTradesData();
  }, [loadTradesData]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  // Filtered and Sorted Trades
  const processedTrades = useMemo(() => {
    return [...trades]
      .filter((t) => {
        if (statusFilter !== "all" && t.status?.toLowerCase() !== statusFilter.toLowerCase()) {
          return false;
        }
        if (sideFilter !== "all" && t.side?.toUpperCase() !== sideFilter.toUpperCase()) {
          return false;
        }
        if (
          searchSymbol.trim() &&
          !t.symbol.toUpperCase().includes(searchSymbol.trim().toUpperCase())
        ) {
          return false;
        }
        return true;
      })
      .sort((a, b) => {
        let diff = 0;
        switch (sortField) {
          case "entry_time":
            diff = new Date(a.entry_time).getTime() - new Date(b.entry_time).getTime();
            break;
          case "symbol":
            diff = a.symbol.localeCompare(b.symbol);
            break;
          case "side":
            diff = a.side.localeCompare(b.side);
            break;
          case "quantity":
            diff = a.quantity - b.quantity;
            break;
          case "realized_pnl":
            diff = (a.realized_pnl ?? 0) - (b.realized_pnl ?? 0);
            break;
        }
        return sortDirection === "asc" ? diff : -diff;
      });
  }, [trades, statusFilter, sideFilter, searchSymbol, sortField, sortDirection]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2">
            <History className="h-5 w-5 text-blue-400" />
            <span>Trades History & Audit Ledger</span>
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Log of algorithmic executions, multi-model consensus decisions, and post-trade reflections
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={loadTradesData}
          loading={loading}
          leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
        >
          Refresh Trades
        </Button>
      </div>

      {/* Summary Stats Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Trades"
          value={stats?.total_trades ?? trades.length}
          subtitle={`${stats?.winning_trades ?? 0} Wins • ${stats?.losing_trades ?? 0} Losses`}
          icon={<History className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Win Rate"
          value={`${stats?.win_rate !== undefined ? (stats.win_rate * 100).toFixed(1) : "0.0"}%`}
          changeLabel="statistical edge"
          icon={<Award className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Total Realized P&L"
          value={formatINR(stats?.total_realized_pnl ?? 0)}
          isPositive={(stats?.total_realized_pnl ?? 0) >= 0}
          icon={<TrendingUp className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Profit Factor"
          value={stats?.profit_factor ? stats.profit_factor.toFixed(2) : "0.00"}
          subtitle="Gross Profit / Gross Loss"
          loading={loading}
        />
      </div>

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4 flex flex-col sm:flex-row items-center gap-3">
          <div className="w-full sm:w-56">
            <Input
              placeholder="Search by symbol..."
              value={searchSymbol}
              onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
            />
          </div>
          <div className="w-full sm:w-44">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              options={[
                { value: "all", label: "All Status" },
                { value: "closed", label: "Closed" },
                { value: "open", label: "Open" },
                { value: "pending", label: "Pending" },
              ]}
            />
          </div>
          <div className="w-full sm:w-40">
            <Select
              value={sideFilter}
              onChange={(e) => setSideFilter(e.target.value)}
              options={[
                { value: "all", label: "All Sides" },
                { value: "BUY", label: "BUY" },
                { value: "SELL", label: "SELL" },
              ]}
            />
          </div>
          <div className="ml-auto text-xs text-gray-400">
            Showing <span className="font-semibold text-white">{processedTrades.length}</span> records
          </div>
        </CardContent>
      </Card>

      {/* Trades Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>Trade Executions</CardTitle>
          <Badge variant="outline" size="sm">
            {processedTrades.length} Records Found
          </Badge>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead
                  className="cursor-pointer hover:text-white"
                  onClick={() => handleSort("entry_time")}
                >
                  <div className="flex items-center gap-1">
                    Date / Time (IST)
                    <ArrowUpDown className="h-3 w-3 text-gray-500" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:text-white"
                  onClick={() => handleSort("symbol")}
                >
                  <div className="flex items-center gap-1">
                    Symbol
                    <ArrowUpDown className="h-3 w-3 text-gray-500" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer hover:text-white"
                  onClick={() => handleSort("side")}
                >
                  <div className="flex items-center gap-1">
                    Side
                    <ArrowUpDown className="h-3 w-3 text-gray-500" />
                  </div>
                </TableHead>
                <TableHead>Mode</TableHead>
                <TableHead
                  className="text-right cursor-pointer hover:text-white"
                  onClick={() => handleSort("quantity")}
                >
                  <div className="flex items-center justify-end gap-1">
                    Quantity
                    <ArrowUpDown className="h-3 w-3 text-gray-500" />
                  </div>
                </TableHead>
                <TableHead className="text-right">Entry Price</TableHead>
                <TableHead className="text-right">Exit Price</TableHead>
                <TableHead
                  className="text-right cursor-pointer hover:text-white"
                  onClick={() => handleSort("realized_pnl")}
                >
                  <div className="flex items-center justify-end gap-1">
                    Realized P&L
                    <ArrowUpDown className="h-3 w-3 text-gray-500" />
                  </div>
                </TableHead>
                <TableHead className="text-center">Audit</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {processedTrades.length > 0 ? (
                processedTrades.map((trade, idx) => {
                  const pnl = trade.realized_pnl ?? 0;
                  const isPositive = pnl >= 0;
                  const isClosed = trade.status === "closed";

                  return (
                    <TableRow key={trade.trade_id || trade.id || `trd_row_${idx}`}>
                      <TableCell className="text-xs text-gray-400 font-mono">
                        {formatDateIST(trade.entry_time)}
                      </TableCell>
                      <TableCell>
                        <span className="font-semibold text-white">{trade.symbol}</span>
                        {trade.strategy && (
                          <span className="block text-[10px] text-gray-500 truncate max-w-[140px]">
                            {trade.strategy}
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={trade.side === "BUY" ? "success" : "danger"}
                          size="sm"
                        >
                          {trade.side}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" size="sm">
                          {trade.mode?.toUpperCase() || "PAPER"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        {trade.quantity}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatINR(trade.entry_price)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {trade.exit_price ? formatINR(trade.exit_price) : "-"}
                      </TableCell>
                      <TableCell className="text-right font-mono font-semibold">
                        {isClosed && trade.realized_pnl !== null && trade.realized_pnl !== undefined ? (
                          <span className={isPositive ? "text-emerald-400" : "text-rose-400"}>
                            {formatINR(pnl)} ({formatPct(trade.realized_pnl_pct)})
                          </span>
                        ) : (
                          <Badge variant="warning" size="sm">
                            OPEN
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedTrade(trade)}
                          leftIcon={<Eye className="h-3.5 w-3.5" />}
                        >
                          Details
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })
              ) : (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8 text-gray-500">
                    {loading ? (
                      <Spinner label="Loading trade records..." center />
                    ) : (
                      "No trade executions found in ledger. Trades will appear here once executed by the engine."
                    )}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Expandable Trade Detail Modal */}
      {selectedTrade && (
        <Modal
          isOpen={Boolean(selectedTrade)}
          onClose={() => setSelectedTrade(null)}
          title={`Trade Audit: ${selectedTrade.symbol} • ${selectedTrade.trade_id}`}
          description={`Entry Time: ${formatDateIST(selectedTrade.entry_time)} ${
            selectedTrade.exit_time ? `• Exit: ${formatDateIST(selectedTrade.exit_time)}` : ""
          }`}
          size="lg"
        >
          <div className="space-y-4">
            {/* Quick Metrics Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-gray-950 p-3.5 rounded-xl border border-gray-800 text-xs">
              <div>
                <span className="text-gray-400">Order Action</span>
                <p className="font-bold text-white mt-0.5 text-sm">
                  {selectedTrade.side} {selectedTrade.quantity} shares
                </p>
              </div>
              <div>
                <span className="text-gray-400">Entry Execution</span>
                <p className="font-bold text-white mt-0.5 font-mono text-sm">
                  {formatINR(selectedTrade.entry_price)}
                </p>
              </div>
              <div>
                <span className="text-gray-400">Exit Execution</span>
                <p className="font-bold text-gray-200 mt-0.5 font-mono text-sm">
                  {selectedTrade.exit_price ? formatINR(selectedTrade.exit_price) : "POSITION OPEN"}
                </p>
              </div>
              <div>
                <span className="text-gray-400">Net Realized P&L</span>
                <p className="font-bold text-emerald-400 mt-0.5 font-mono text-sm">
                  {selectedTrade.realized_pnl !== null && selectedTrade.realized_pnl !== undefined
                    ? formatINR(selectedTrade.realized_pnl)
                    : "UNREALIZED"}
                </p>
              </div>
            </div>

            {/* Model Predictions Breakdown */}
            {selectedTrade.model_predictions && selectedTrade.model_predictions.length > 0 && (
              <div className="space-y-2">
                <span className="text-xs font-semibold text-gray-300 flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-purple-400" />
                  Multi-LLM Swarm Predictions
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {selectedTrade.model_predictions.map((mp, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 rounded-lg border border-gray-800 bg-gray-950/70 text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">{mp.model_name}</span>
                        <Badge
                          variant={mp.prediction === "BUY" ? "success" : "danger"}
                          size="sm"
                        >
                          {mp.prediction}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-gray-400">
                        <span>Confidence:</span>
                        <span className="font-mono text-blue-300 font-bold">{mp.confidence}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Entry & Exit Rationales */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {selectedTrade.entry_rationale && (
                <div className="space-y-1 bg-gray-950/70 p-3 rounded-lg border border-gray-800">
                  <span className="text-xs font-semibold text-blue-400">Entry Rationale</span>
                  <p className="text-xs text-gray-300 leading-relaxed mt-1">
                    {selectedTrade.entry_rationale}
                  </p>
                </div>
              )}

              {selectedTrade.exit_rationale && (
                <div className="space-y-1 bg-gray-950/70 p-3 rounded-lg border border-gray-800">
                  <span className="text-xs font-semibold text-amber-400">Exit Rationale</span>
                  <p className="text-xs text-gray-300 leading-relaxed mt-1">
                    {selectedTrade.exit_rationale}
                  </p>
                </div>
              )}
            </div>

            {/* Post-Trade Reflection & Memory Learning */}
            {selectedTrade.reflection && (
              <div className="space-y-1.5 bg-blue-950/20 p-3.5 rounded-xl border border-blue-900/40">
                <span className="text-xs font-bold text-blue-300 flex items-center gap-1.5">
                  <BookOpen className="h-4 w-4 text-blue-400" />
                  BM25 Agent Reflection & Post-Trade Learning
                </span>
                <p className="text-xs text-gray-200 leading-relaxed">
                  {selectedTrade.reflection.lesson}
                </p>
                {selectedTrade.reflection.outcome_review && (
                  <p className="text-[11px] text-gray-400 mt-1 italic">
                    Review: {selectedTrade.reflection.outcome_review}
                  </p>
                )}
              </div>
            )}

            {/* Macro & Brokerage Execution Context */}
            {selectedTrade.macro_context && (
              <div className="flex items-center justify-between p-2.5 rounded-lg bg-gray-950 border border-gray-850 text-[11px] text-gray-400">
                <span>Nifty Index: <strong className="text-gray-200">{selectedTrade.macro_context.nifty_level ?? "-"}</strong></span>
                <span>India VIX: <strong className="text-gray-200">{selectedTrade.macro_context.india_vix ?? "-"}</strong></span>
                <span>Slippage: <strong className="text-gray-200">{selectedTrade.macro_context.slippage ? `₹${selectedTrade.macro_context.slippage}` : "0"}</strong></span>
                <span>Brokerage: <strong className="text-gray-200">{selectedTrade.macro_context.brokerage ? `₹${selectedTrade.macro_context.brokerage}` : "₹20"}</strong></span>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
