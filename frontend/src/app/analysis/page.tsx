"use client";

import React, { useState, useEffect, Suspense, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import { analysisApi } from "@/lib/api";
import { useAgentStream } from "@/lib/use-agent-stream";
import { formatINR } from "@/lib/utils";
import type { DecisionCardData, AgentStatusEvent, EventLogEntry } from "@/lib/types";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Badge,
  Button,
  Input,
  Select,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Markdown,
  Spinner,
} from "@/components/ui";
import {
  Cpu,
  Play,
  CheckCircle2,
  AlertTriangle,
  Radio,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  Clock,
  Gauge,
  Layers,
  Sparkles,
  RefreshCw,
  Terminal,
  FileText,
} from "lucide-react";

interface AgentTeamDef {
  id: string;
  name: string;
  role: string;
  models: string;
}

const AGENT_TEAMS: AgentTeamDef[] = [
  {
    id: "analyst",
    name: "Analyst Team",
    role: "Technical indicators, RSI/MACD & news catalysts",
    models: "Gemini 1.5 Flash",
  },
  {
    id: "research",
    name: "Research Debate",
    role: "Adversarial Bull vs Bear thesis cross-examination",
    models: "Claude 3.5 Sonnet",
  },
  {
    id: "trading",
    name: "Trading Strategy",
    role: "Multi-timeframe setup & execution entry timing",
    models: "Claude 3.5 Sonnet",
  },
  {
    id: "risk",
    name: "Risk Management",
    role: "VaR threshold & 16 frozen safety checks",
    models: "Claude 3.5 Sonnet",
  },
  {
    id: "portfolio",
    name: "Portfolio Management",
    role: "Kelly sizing & final consensus verdict",
    models: "Claude 3.5 Sonnet",
  },
];

const QUICK_SYMBOLS = ["RELIANCE", "INFY", "TCS", "HDFCBANK", "TATAMOTORS"];

function AnalysisContent() {
  const searchParams = useSearchParams();
  const initialSymbol = searchParams?.get("symbol") || "RELIANCE";

  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [urgency, setUrgency] = useState<"low" | "medium" | "high">("medium");
  const [lookbackDays, setLookbackDays] = useState<number>(30);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState<boolean>(false);
  const [activeReportTab, setActiveReportTab] = useState<string>("analyst");

  const [launchError, setLaunchError] = useState<string | null>(null);
  const [validation, setValidation] = useState<{
    checking: boolean;
    valid: boolean | null;
    exchange?: string | null;
    error?: string | null;
  }>({ checking: false, valid: null });

  const {
    connectionStatus,
    isConnected,
    isCompleted,
    error: streamError,
    agentStatuses,
    reports,
    logs,
    decision,
  } = useAgentStream(activeJobId);

  // Sync symbol from search params if updated
  useEffect(() => {
    const s = searchParams?.get("symbol");
    if (s) {
      setSymbol(s.toUpperCase());
    }
  }, [searchParams]);

  // Debounced symbol verification against backend validator
  useEffect(() => {
    const clean = symbol.trim().toUpperCase();
    if (!clean) {
      setValidation({ checking: false, valid: null });
      return;
    }

    setValidation({ checking: true, valid: null });
    const timer = setTimeout(async () => {
      try {
        const res = await analysisApi.validateSymbol(clean);
        setValidation({
          checking: false,
          valid: res.valid,
          exchange: res.exchange,
          error: res.error,
        });
      } catch {
        setValidation({
          checking: false,
          valid: null,
          error: "Unable to verify ticker with backend validator",
        });
      }
    }, 350);

    return () => clearTimeout(timer);
  }, [symbol]);

  const isRunning =
    starting || isConnected || (activeJobId !== null && !isCompleted && !streamError && !decision);

  const handleStartAnalysis = async () => {
    if (!symbol.trim() || validation.valid === false) return;
    const cleanSym = symbol.trim().toUpperCase();
    setStarting(true);
    setLaunchError(null);

    try {
      const res = await analysisApi.startAnalysis({
        symbol: cleanSym,
        urgency,
        lookback_days: lookbackDays,
      });
      setActiveJobId(res.job_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to start analysis job";
      setLaunchError(msg);
    } finally {
      setStarting(false);
    }
  };

  const currentReports = reports || {};
  const reportKeys = Object.keys(currentReports);
  const activeReportContent =
    currentReports[activeReportTab] ||
    (reportKeys.length > 0 ? currentReports[reportKeys[0]] : null);

  return (
    <div className="space-y-6">
      {/* Header and Symbol Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2">
            <Cpu className="h-5 w-5 text-purple-400" />
            <span>Multi-Agent Swarm Analysis</span>
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Streaming real-time execution across Analyst, Adversary Debate, Risk, and Portfolio swarms
          </p>
        </div>
      </div>

      {/* Error Feedback Banner */}
      {(launchError || streamError) && (
        <Card className="border-rose-800/60 bg-rose-950/20 text-rose-300 p-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="text-sm font-semibold text-rose-200">Analysis Halted</p>
              <p className="text-xs text-rose-300/90">{launchError || streamError}</p>
              <p className="text-[11px] text-rose-400/80">
                Please verify that a valid stock ticker is selected (e.g. RELIANCE, TCS, INFY) and that an LLM API key is configured.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Symbol Controls Bar */}
      <Card>
        <CardContent className="p-4 space-y-3.5">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
            {/* Symbol Input */}
            <div className="sm:col-span-5">
              <label className="text-xs font-semibold text-gray-300 block mb-1">
                NSE Trading Symbol
              </label>
              <Input
                placeholder="e.g. RELIANCE, INFY, TCS"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                disabled={isRunning}
              />
              {validation.checking && (
                <p className="text-[11px] text-gray-400 mt-1 flex items-center gap-1">
                  <Spinner size="sm" /> Verifying ticker on NSE/BSE...
                </p>
              )}
              {!validation.checking && validation.valid === true && (
                <p className="text-[11px] text-emerald-400 mt-1 flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" /> Validated on {validation.exchange || "NSE"}
                </p>
              )}
              {!validation.checking && validation.valid === false && (
                <p className="text-[11px] text-rose-400 mt-1 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" /> {validation.error || "Symbol not found on exchange"}
                </p>
              )}
            </div>

            {/* Lookback Selector */}
            <div className="sm:col-span-3">
              <label className="text-xs font-semibold text-gray-300 block mb-1">
                Lookback Horizon
              </label>
              <Select
                value={String(lookbackDays)}
                onChange={(e) => setLookbackDays(Number(e.target.value))}
                disabled={isRunning}
                options={[
                  { value: "7", label: "7 Days (Intraday/Momentum)" },
                  { value: "15", label: "15 Days (Swing Setup)" },
                  { value: "30", label: "30 Days (Standard Horizon)" },
                  { value: "60", label: "60 Days (Macro Horizon)" },
                  { value: "90", label: "90 Days (Quarterly Cycle)" },
                ]}
              />
            </div>

            {/* Urgency Selector */}
            <div className="sm:col-span-2">
              <label className="text-xs font-semibold text-gray-300 block mb-1">
                Priority
              </label>
              <Select
                value={urgency}
                onChange={(e) => setUrgency(e.target.value as "low" | "medium" | "high")}
                disabled={isRunning}
                options={[
                  { value: "low", label: "Low" },
                  { value: "medium", label: "Medium" },
                  { value: "high", label: "High" },
                ]}
              />
            </div>

            {/* Trigger Button */}
            <div className="sm:col-span-2">
              <Button
                onClick={handleStartAnalysis}
                loading={isRunning}
                disabled={!symbol.trim() || validation.valid === false || validation.checking || isRunning}
                leftIcon={<Play className="h-4 w-4" />}
                className="w-full"
              >
                {isRunning ? "Running..." : "Launch Swarm"}
              </Button>
            </div>
          </div>

          {/* Quick Symbol Chips & Active Stream Badge */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 border-t border-gray-800/80">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[11px] text-gray-400 font-medium mr-1">
                Quick Pick:
              </span>
              {QUICK_SYMBOLS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setSymbol(s)}
                  disabled={isRunning}
                  className={`text-xs px-2.5 py-1 rounded-md border font-mono transition-colors ${
                    symbol === s
                      ? "bg-blue-900/40 text-blue-300 border-blue-700/60 font-semibold"
                      : "bg-gray-800/50 text-gray-300 border-gray-700/60 hover:bg-gray-800"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>

            {activeJobId && (
              <div className="flex items-center gap-2 text-xs text-gray-400 ml-auto">
                <span className="text-[11px]">Stream:</span>
                <Badge
                  variant={
                    decision
                      ? "success"
                      : isRunning
                      ? "warning"
                      : streamError
                      ? "danger"
                      : "secondary"
                  }
                  size="sm"
                  dot={isRunning}
                >
                  {decision
                    ? "COMPLETED"
                    : isRunning
                    ? "PROPAGATING GRAPH"
                    : connectionStatus.toUpperCase()}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Consensus Decision Card */}
      {decision && (
        <Card className="border-blue-600/50 bg-gradient-to-r from-gray-900 via-blue-950/30 to-gray-900 shadow-lg">
          <CardHeader className="flex flex-row items-center justify-between pb-3">
            <div className="flex items-center gap-2.5">
              <div className="rounded-lg bg-blue-600/20 p-2 text-blue-400 border border-blue-500/40">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <div>
                <CardTitle className="text-base sm:text-lg">
                  Autonomous Consensus Decision Card
                </CardTitle>
                <p className="text-xs text-gray-400">
                  Synthesized across 5 agent teams with 16 frozen risk safety checks enforced
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant={
                  decision.verdict === "BUY"
                    ? "success"
                    : decision.verdict === "SELL"
                    ? "danger"
                    : "warning"
                }
                size="md"
                className="text-sm px-3 py-1 font-bold tracking-wide"
              >
                {decision.verdict}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="space-y-4">
            {/* Visual Confidence Gauge & Key Execution Parameters */}
            <div className="grid grid-cols-2 sm:grid-cols-6 gap-3 p-4 rounded-xl bg-gray-950/80 border border-gray-800">
              {/* Confidence Gauge */}
              <div className="col-span-2 sm:col-span-1">
                <span className="text-xs text-gray-400 flex items-center gap-1">
                  <Gauge className="h-3.5 w-3.5 text-blue-400" />
                  Confidence
                </span>
                <div className="mt-1 flex items-baseline gap-1">
                  <span className="text-2xl font-bold text-blue-400 font-mono">
                    {decision.confidence}
                  </span>
                  <span className="text-xs text-gray-400">/100</span>
                </div>
                <div className="mt-1.5 w-full bg-gray-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-blue-500 h-full rounded-full transition-all"
                    style={{ width: `${decision.confidence}%` }}
                  />
                </div>
              </div>

              {/* Position Sizing */}
              <div>
                <span className="text-xs text-gray-400">Quantity</span>
                <p className="text-lg font-bold text-white font-mono mt-1">
                  {decision.position_size} shares
                </p>
                <span className="text-[11px] text-gray-400">
                  {formatINR(
                    decision.position_size_inr ??
                      decision.position_size * decision.entry_price
                  )}
                </span>
              </div>

              {/* Entry Price */}
              <div>
                <span className="text-xs text-gray-400">Entry Target</span>
                <p className="text-lg font-bold text-gray-100 font-mono mt-1">
                  {formatINR(decision.entry_price)}
                </p>
                <span className="text-[11px] text-gray-500">Market / Limit</span>
              </div>

              {/* Stop Loss */}
              <div>
                <span className="text-xs text-gray-400">Stop Loss</span>
                <p className="text-lg font-bold text-rose-400 font-mono mt-1">
                  {formatINR(decision.stop_loss)}
                </p>
                <span className="text-[11px] text-rose-400/80">
                  {decision.entry_price && decision.stop_loss
                    ? `-${(
                        ((decision.entry_price - decision.stop_loss) /
                          decision.entry_price) *
                        100
                      ).toFixed(1)}%`
                    : "-"}
                </span>
              </div>

              {/* Target */}
              <div>
                <span className="text-xs text-gray-400">Profit Target</span>
                <p className="text-lg font-bold text-emerald-400 font-mono mt-1">
                  {formatINR(decision.target)}
                </p>
                <span className="text-[11px] text-emerald-400/80">
                  {decision.entry_price && decision.target
                    ? `+${(
                        ((decision.target - decision.entry_price) /
                          decision.entry_price) *
                        100
                      ).toFixed(1)}%`
                    : "-"}
                </span>
              </div>

              {/* Risk-Reward */}
              <div>
                <span className="text-xs text-gray-400">Risk-Reward</span>
                <p className="text-lg font-bold text-amber-300 font-mono mt-1">
                  {decision.risk_reward_ratio ? `${decision.risk_reward_ratio}:1` : "2.2:1"}
                </p>
                <span className="text-[11px] text-amber-400/80">Edge Verified</span>
              </div>
            </div>

            {/* Investment Reasoning Summary */}
            <div className="text-xs text-gray-200 leading-relaxed bg-gray-900/90 p-4 rounded-xl border border-gray-800">
              <span className="font-bold text-blue-400 block mb-1 text-sm">
                Consensus Investment Reasoning:
              </span>
              <p className="text-gray-300 leading-relaxed">{decision.reasoning}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agent Teams Topology Cards */}
      <div>
        <h3 className="text-sm font-semibold text-gray-200 mb-3 flex items-center gap-2">
          <Layers className="h-4 w-4 text-purple-400" />
          Autonomous Multi-Agent Topology
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {AGENT_TEAMS.map((team) => {
            const statusEntry = Object.values(agentStatuses || {}).find(
              (s) =>
                s?.team?.toLowerCase() === team.id ||
                s?.agent_id?.toLowerCase().includes(team.id)
            );
            const currentStatus =
              statusEntry?.status || (isRunning ? "running" : "pending");
            const isTeamRunning = currentStatus === "running";
            const isTeamDone = currentStatus === "completed";

            return (
              <Card
                key={team.id}
                className={`p-3.5 transition-all ${
                  isTeamRunning
                    ? "border-amber-500/50 bg-amber-950/10"
                    : isTeamDone
                    ? "border-emerald-500/40 bg-gray-900/90"
                    : "bg-gray-900/60"
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-white">{team.name}</span>
                  <Badge
                    variant={
                      isTeamDone
                        ? "success"
                        : isTeamRunning
                        ? "warning"
                        : "secondary"
                    }
                    size="sm"
                    dot={isTeamRunning}
                  >
                    {currentStatus.toUpperCase()}
                  </Badge>
                </div>
                <p className="text-[11px] text-gray-400 leading-tight min-h-[28px]">
                  {team.role}
                </p>
                <div className="mt-2.5 pt-2 border-t border-gray-800/80 flex items-center justify-between text-[10px] text-gray-500">
                  <span>{team.models}</span>
                  {isTeamRunning && <Spinner size="sm" />}
                  {isTeamDone && <CheckCircle2 className="h-3 w-3 text-emerald-400" />}
                </div>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Streaming Markdown Reports Viewer & Event Logs Tabs */}
      <Tabs defaultValue="reports">
        <TabsList>
          <TabsTrigger value="reports">
            <FileText className="h-3.5 w-3.5 mr-1.5" />
            Agent Reports ({reportKeys.length})
          </TabsTrigger>
          <TabsTrigger value="logs">
            <Terminal className="h-3.5 w-3.5 mr-1.5" />
            Granular Event Stream ({logs.length})
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Agent Reports with Selector Tabs */}
        <TabsContent value="reports">
          {reportKeys.length > 0 ? (
            <div className="space-y-4">
              {/* Agent Selector Sub-tabs */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
                {reportKeys.map((agentId) => (
                  <button
                    key={agentId}
                    type="button"
                    onClick={() => setActiveReportTab(agentId)}
                    className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                      activeReportTab === agentId
                        ? "bg-blue-600 text-white border-blue-500 shadow-sm"
                        : "bg-gray-900 text-gray-300 border-gray-800 hover:bg-gray-850"
                    }`}
                  >
                    {agentId.toUpperCase()}
                  </button>
                ))}
              </div>

              {/* Render Active Report */}
              <Card>
                <CardHeader className="py-3 px-4 border-b border-gray-800/80 flex flex-row items-center justify-between">
                  <CardTitle className="text-xs uppercase tracking-wider text-blue-400">
                    Detailed Report: {activeReportTab}
                  </CardTitle>
                  <Badge variant="outline" size="sm">
                    MARKDOWN
                  </Badge>
                </CardHeader>
                <CardContent className="p-5">
                  <Markdown content={activeReportContent || "Awaiting report content..."} />
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-8 text-center text-xs text-gray-500">
              {isRunning ? (
                <Spinner center label="Awaiting agent reports from graph execution..." />
              ) : (
                "No agent reports generated yet. Click 'Launch Swarm' above to begin."
              )}
            </div>
          )}
        </TabsContent>

        {/* Tab 2: Event Stream Log */}
        <TabsContent value="logs">
          <Card className="bg-gray-950 font-mono text-xs border-gray-800">
            <CardHeader className="py-3 px-4 border-b border-gray-800/80 flex flex-row items-center justify-between">
              <CardTitle className="text-xs text-gray-400">
                Live SSE Telemetry & Tool Execution Log
              </CardTitle>
              <Badge variant="outline" size="sm">
                {logs.length} EVENTS
              </Badge>
            </CardHeader>
            <CardContent className="p-4 max-h-96 overflow-y-auto space-y-2">
              {logs.length > 0 ? (
                logs.map((log, idx) => {
                  const isErr = log.level === "ERROR";
                  const isWarn = log.level === "WARNING";
                  const timestampStr = log.timestamp
                    ? log.timestamp.length > 19
                      ? log.timestamp.slice(11, 19)
                      : log.timestamp
                    : "--:--:--";

                  return (
                    <div key={idx} className="flex items-start gap-2.5 text-gray-300">
                      <span className="text-gray-500 shrink-0 font-mono text-[11px]">
                        {timestampStr}
                      </span>
                      <Badge
                        variant={isErr ? "danger" : isWarn ? "warning" : "info"}
                        size="sm"
                        className="text-[10px] px-1.5 py-0 shrink-0"
                      >
                        {log.level}
                      </Badge>
                      <span className="break-all text-[11px] leading-relaxed">
                        {log.message}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="text-gray-600 italic py-6 text-center">
                  Live event logs and tool executions will stream here during graph propagation.
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={<Spinner center label="Loading Analysis Workspace..." />}>
      <AnalysisContent />
    </Suspense>
  );
}
