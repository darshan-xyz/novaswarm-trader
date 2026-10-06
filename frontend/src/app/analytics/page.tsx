"use client";

import React, { useState, useEffect } from "react";
import { performanceApi } from "@/lib/api";
import type {
  PerformanceMetrics,
  DailySnapshot,
  ModelAccuracy,
} from "@/lib/types";
import { formatINR, formatPct } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  StatCard,
  Badge,
  Spinner,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import {
  TrendingUp,
  Award,
  Activity,
  ShieldAlert,
  Sparkles,
  BarChart2,
  LineChart,
} from "lucide-react";

const BASELINE_SNAPSHOT: DailySnapshot[] = [
  { date: "Today", equity: 1000000, realized_pnl: 0, unrealized_pnl: 0, drawdown_pct: 0 },
];

export default function AnalyticsPage() {
  const [mounted, setMounted] = useState(false);
  const [metrics, setMetrics] = useState<PerformanceMetrics | null>(null);
  const [snapshots, setSnapshots] = useState<DailySnapshot[]>([]);
  const [modelAccuracies, setModelAccuracies] = useState<ModelAccuracy[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setMounted(true);
    const loadAnalytics = async () => {
      setLoading(true);
      try {
        const [mRes, sRes, accRes] = await Promise.allSettled([
          performanceApi.getMetrics(),
          performanceApi.getDailySnapshots(),
          performanceApi.getModelAccuracy(),
        ]);

        if (mRes.status === "fulfilled" && mRes.value) {
          setMetrics(mRes.value);
        } else {
          setMetrics({
            win_rate: 0.0,
            sharpe_ratio: 0.0,
            max_drawdown: 0.0,
            total_pnl: 0.0,
            profit_factor: 0.0,
            total_trades: 0,
            win_loss_ratio: 0.0,
          });
        }

        if (sRes.status === "fulfilled" && Array.isArray(sRes.value) && sRes.value.length > 0) {
          setSnapshots(sRes.value);
        } else {
          setSnapshots(BASELINE_SNAPSHOT);
        }

        if (accRes.status === "fulfilled" && Array.isArray(accRes.value)) {
          setModelAccuracies(accRes.value);
        } else {
          setModelAccuracies([]);
        }
      } catch {
        setMetrics({
          win_rate: 0.0,
          sharpe_ratio: 0.0,
          max_drawdown: 0.0,
          total_pnl: 0.0,
          profit_factor: 0.0,
          total_trades: 0,
          win_loss_ratio: 0.0,
        });
        setSnapshots(BASELINE_SNAPSHOT);
        setModelAccuracies([]);
      } finally {
        setLoading(false);
      }
    };

    loadAnalytics();
  }, []);

  const chartData = snapshots.length > 0 ? snapshots : BASELINE_SNAPSHOT;
  const modelsData = modelAccuracies;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2">
          <BarChart2 className="h-5 w-5 text-blue-400" />
          <span>Performance Analytics & Quantitative Edge</span>
        </h2>
        <p className="text-xs text-gray-400 mt-0.5">
          Equity growth trajectory, daily return distribution with dynamic loss bars, and multi-model accuracy breakdown
        </p>
      </div>

      {/* 4 Required KPI Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Sharpe Ratio"
          value={metrics?.sharpe_ratio ? metrics.sharpe_ratio.toFixed(2) : "0.00"}
          subtitle="Risk-adjusted annualized edge"
          icon={<TrendingUp className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Win Rate"
          value={`${metrics?.win_rate !== undefined ? (metrics.win_rate * 100).toFixed(1) : "0.0"}%`}
          subtitle="Profitable trade percentage"
          icon={<Award className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Max Drawdown"
          value={`${metrics?.max_drawdown ? metrics.max_drawdown.toFixed(2) : "0.00"}%`}
          subtitle="Peak-to-trough preservation"
          isPositive={false}
          icon={<ShieldAlert className="h-4 w-4" />}
          loading={loading}
        />
        <StatCard
          title="Average Win / Loss"
          value={`${metrics?.win_loss_ratio ? metrics.win_loss_ratio.toFixed(2) : "0.00"}x`}
          subtitle={metrics?.total_trades ? "Avg Win vs Avg Loss" : "No trade history recorded"}
          icon={<Activity className="h-4 w-4" />}
          loading={loading}
        />
      </div>

      {/* Charts Grid: AreaChart and BarChart */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Equity Growth Curve */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div>
              <CardTitle className="flex items-center gap-2">
                <LineChart className="h-4 w-4 text-blue-400" />
                <span>Equity Growth Curve</span>
              </CardTitle>
              <p className="text-xs text-gray-400 mt-0.5">
                Compounded portfolio trajectory in INR
              </p>
            </div>
            <Badge variant="outline" size="sm">
              AREA GRADIENT
            </Badge>
          </CardHeader>
          <CardContent className="h-72">
            {mounted ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.45} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="date" stroke="#6b7280" fontSize={11} tickLine={false} />
                  <YAxis
                    stroke="#6b7280"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => `₹${(val / 100000).toFixed(1)}L`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#111827",
                      borderColor: "#374151",
                      borderRadius: "8px",
                      fontSize: "12px",
                      color: "#f3f4f6",
                    }}
                    formatter={(val: unknown) => [formatINR(Number(val)), "Portfolio Equity"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="equity"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#equityGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <Spinner center label="Loading visual equity curve..." />
            )}
          </CardContent>
        </Card>

        {/* Daily P&L Distribution with Dynamic Red/Green Bars */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div>
              <CardTitle className="flex items-center gap-2">
                <BarChart2 className="h-4 w-4 text-emerald-400" />
                <span>Daily Realized P&L</span>
              </CardTitle>
              <p className="text-xs text-gray-400 mt-0.5">
                Session P&L with dynamic profit (green) and loss (red) bars
              </p>
            </div>
            <Badge variant="outline" size="sm">
              DYNAMIC BARS
            </Badge>
          </CardHeader>
          <CardContent className="h-72">
            {mounted ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                  <XAxis dataKey="date" stroke="#6b7280" fontSize={11} tickLine={false} />
                  <YAxis
                    stroke="#6b7280"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#111827",
                      borderColor: "#374151",
                      borderRadius: "8px",
                      fontSize: "12px",
                      color: "#f3f4f6",
                    }}
                    formatter={(val: unknown) => [formatINR(Number(val)), "Realized P&L"]}
                  />
                  <Bar dataKey="realized_pnl" radius={[4, 4, 0, 0]}>
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.realized_pnl >= 0 ? "#10b981" : "#f43f5e"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Spinner center label="Loading daily P&L chart..." />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Per-Model Prediction Accuracy Breakdown */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-purple-400" />
              <span>Per-Model Prediction Accuracy Breakdown</span>
            </CardTitle>
            <p className="text-xs text-gray-400 mt-0.5">
              Empirical verification of individual agent predictions against realized market outcomes
            </p>
          </div>
          <Badge variant="outline" size="sm">
            {modelsData.length} Models Active
          </Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          {modelsData.length > 0 ? (
            <>
          {/* Visual Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {modelsData.map((mod) => {
              const accPct = typeof mod.accuracy_pct === "number" ? mod.accuracy_pct : 0;
              const avgConf = typeof mod.avg_confidence === "number" ? mod.avg_confidence : 0;
              return (
                <div
                  key={mod.model_name}
                  className="rounded-xl border border-gray-800 bg-gray-950/70 p-3.5 space-y-2 hover:border-gray-700 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white truncate max-w-[130px]">
                      {mod.model_name}
                    </span>
                    <Badge variant="success" size="sm">
                      {accPct.toFixed(1)}%
                    </Badge>
                  </div>
                  <div className="w-full bg-gray-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className="bg-emerald-500 h-full rounded-full"
                      style={{ width: `${Math.min(Math.max(accPct, 0), 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[11px] text-gray-400 pt-1 font-mono">
                    <span>{mod.total_predictions ?? 0} trades</span>
                    <span>{avgConf.toFixed(1)}% conf</span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Detailed Accuracy Table */}
          <div className="rounded-xl border border-gray-800 overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Model Name</TableHead>
                  <TableHead>Inference Provider</TableHead>
                  <TableHead className="text-right">Total Predictions</TableHead>
                  <TableHead className="text-right">Accurate (Wins)</TableHead>
                  <TableHead className="text-right">Accuracy %</TableHead>
                  <TableHead className="text-right">Avg Confidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {modelsData.map((mod) => {
                  const accPct = typeof mod.accuracy_pct === "number" ? mod.accuracy_pct : 0;
                  const avgConf = typeof mod.avg_confidence === "number" ? mod.avg_confidence : 0;
                  const provider =
                    (mod as any).provider ||
                    (mod.model_name.includes("Claude")
                      ? "Anthropic"
                      : mod.model_name.includes("Gemini")
                      ? "Google"
                      : mod.model_name.includes("Sonar")
                      ? "Perplexity"
                      : mod.model_name.includes("Grok")
                      ? "xAI"
                      : "Ollama");

                  return (
                    <TableRow key={mod.model_name}>
                      <TableCell className="font-semibold text-white">
                        {mod.model_name}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" size="sm">
                          {provider}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono font-medium">
                        {mod.total_predictions ?? 0}
                      </TableCell>
                      <TableCell className="text-right font-mono text-emerald-400 font-semibold">
                        {mod.accurate_predictions ?? 0}
                      </TableCell>
                      <TableCell className="text-right font-mono font-bold text-white">
                        {accPct.toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-right font-mono text-blue-300">
                        {avgConf.toFixed(1)}%
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
            </>
          ) : (
            <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-8 text-center text-xs text-gray-500">
              No model predictions recorded yet. Agent recommendations will populate accuracy metrics as trades resolve.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
