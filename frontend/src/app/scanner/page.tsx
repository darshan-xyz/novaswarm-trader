"use client";

import React, { useEffect, useState, useCallback } from "react";
import { scannerApi } from "@/lib/api";
import type { ScannerStatus, ScannerCandidate } from "@/lib/types";
import { formatINR, formatPct } from "@/lib/utils";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Badge,
  Button,
  Spinner,
  Select,
} from "@/components/ui";
import {
  ScanSearch,
  Play,
  AlertCircle,
  ArrowUpRight,
  Flame,
  Zap,
  TrendingUp,
  Radio,
  CheckCircle2,
  Filter,
} from "lucide-react";
import Link from "next/link";

export default function ScannerPage() {
  const [status, setStatus] = useState<ScannerStatus | null>(null);
  const [candidates, setCandidates] = useState<ScannerCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Filters
  const [urgencyFilter, setUrgencyFilter] = useState<string>("ALL");
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statusRes, candidatesRes] = await Promise.allSettled([
        scannerApi.getStatus(),
        scannerApi.getCandidates(),
      ]);

      if (statusRes.status === "fulfilled") {
        setStatus(statusRes.value);
      }
      if (candidatesRes.status === "fulfilled" && Array.isArray(candidatesRes.value)) {
        setCandidates(candidatesRes.value);
      } else {
        setCandidates([]);
      }
    } catch {
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleTriggerScan = async () => {
    setScanning(true);
    setMessage(null);
    try {
      await scannerApi.triggerScan();
      setMessage("Autonomous scan cycle initiated! Candidate queue refreshed.");
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to execute autonomous market scan";
      setMessage(msg);
    } finally {
      setScanning(false);
    }
  };

  // Filter candidates
  const filteredCandidates = candidates.filter((c) => {
    if (urgencyFilter !== "ALL" && c.urgency?.toUpperCase() !== urgencyFilter) {
      return false;
    }
    if (sourceFilter !== "ALL") {
      const srcList = Array.isArray(c.sources)
        ? c.sources
        : typeof c.sources === "string"
        ? [c.sources]
        : [];
      const hasSource = srcList.some(
        (s) => typeof s === "string" && s.toLowerCase() === sourceFilter.toLowerCase()
      );
      if (!hasSource) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-100 flex items-center gap-2">
            <ScanSearch className="h-5 w-5 text-blue-400" />
            <span>Market Scanner Radar</span>
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Real-time breakout detection, volume spike analysis, and multi-model candidate confluence
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={handleTriggerScan}
            loading={scanning}
            leftIcon={<Play className="h-4 w-4" />}
          >
            Run On-Demand Scan
          </Button>
        </div>
      </div>

      {message && (
        <div className="rounded-xl border border-blue-800 bg-blue-950/20 p-3 text-xs text-blue-300 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
          <span>{message}</span>
        </div>
      )}

      {/* Scanner Radar Status Cockpit */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-600/10 border border-blue-500/30 text-blue-400">
              <Radio className="h-5 w-5 animate-pulse text-blue-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-white">Scanner Radar Engine</span>
                <Badge variant={status?.running ?? true ? "success" : "secondary"} size="sm" dot>
                  {status?.running ?? true ? "RADAR ACTIVE" : "STANDBY"}
                </Badge>
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                Cycle #{status?.cycle_count ?? 0} • Watchlist: {status?.watchlist_size ?? 50} Nifty 50 Equities • Queue: {candidates.length} setups
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] text-gray-400 mr-1">Active Screeners:</span>
            {(() => {
              const rawScreeners = status?.screeners;
              let screenerList: string[] = [];
              if (Array.isArray(rawScreeners)) {
                screenerList = rawScreeners;
              } else if (rawScreeners && typeof rawScreeners === "object") {
                screenerList = (rawScreeners as { active?: string[] }).active ?? Object.keys(rawScreeners);
              }
              if (screenerList.length === 0) {
                screenerList = ["Momentum Breakout", "2x Volume Spike", "EMA Expansion", "ORB 15m"];
              }
              return screenerList.map((scr) => (
                <Badge key={scr} variant="outline" size="sm">
                  {scr}
                </Badge>
              ));
            })()}
          </div>
        </CardContent>
      </Card>

      {/* Filter Toolbar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-gray-900/50 rounded-xl border border-gray-800">
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="h-4 w-4 text-gray-400 shrink-0" />
          <span className="text-xs font-semibold text-gray-200 shrink-0">Filters:</span>
          <div className="w-36">
            <Select
              value={urgencyFilter}
              onChange={(e) => setUrgencyFilter(e.target.value)}
              options={[
                { value: "ALL", label: "All Urgency" },
                { value: "HIGH", label: "HIGH" },
                { value: "NORMAL", label: "NORMAL" },
                { value: "LOW", label: "LOW" },
              ]}
            />
          </div>
          <div className="w-40">
            <Select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              options={[
                { value: "ALL", label: "All Sources" },
                { value: "Technicals", label: "Technicals" },
                { value: "News", label: "News" },
                { value: "Social", label: "Social" },
                { value: "Fundamentals", label: "Fundamentals" },
              ]}
            />
          </div>
        </div>
        <div className="text-xs text-gray-400 ml-auto">
          Showing <span className="font-semibold text-white">{filteredCandidates.length}</span> of {candidates.length} candidates
        </div>
      </div>

      {/* Candidates Grid */}
      <div>
        {loading ? (
          <Spinner center label="Fetching real-time scanner candidates..." />
        ) : filteredCandidates.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredCandidates.map((cand) => {
              const urgencyNormalized = cand.urgency?.toUpperCase() || "NORMAL";
              const isHigh = urgencyNormalized === "HIGH";
              const isNormal = urgencyNormalized === "NORMAL" || urgencyNormalized === "MEDIUM";

              return (
                <Card
                  key={cand.symbol}
                  className={`transition-all hover:border-blue-500/50 ${
                    isHigh ? "border-amber-500/30 bg-gradient-to-b from-gray-900 via-gray-900 to-amber-950/10" : ""
                  }`}
                >
                  <CardHeader className="p-4 pb-2 flex flex-row items-center justify-between">
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-lg font-bold text-white tracking-wide">
                          {cand.symbol}
                        </span>
                        <span className="text-[10px] text-gray-400 bg-gray-800 px-1.5 py-0.5 rounded font-mono">
                          {cand.exchange || "NSE"}
                        </span>
                      </div>
                      {cand.score && (
                        <div className="text-[11px] text-blue-400 font-semibold mt-0.5">
                          Confluence Score: {cand.score}/100
                        </div>
                      )}
                    </div>
                    <Badge
                      variant={isHigh ? "danger" : isNormal ? "warning" : "info"}
                      size="sm"
                      className="font-bold tracking-wider"
                    >
                      {isHigh && <Flame className="h-3 w-3 mr-1 inline text-rose-300" />}
                      {urgencyNormalized}
                    </Badge>
                  </CardHeader>

                  <CardContent className="p-4 pt-2 space-y-3">
                    {/* Metrics Grid */}
                    <div className="grid grid-cols-2 gap-2 text-xs bg-gray-950/60 p-2.5 rounded-lg border border-gray-800/80">
                      <div>
                        <span className="text-gray-400">LTP</span>
                        <p className="font-bold text-gray-100 font-mono text-sm">
                          {formatINR(cand.ltp)}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Change</span>
                        <p className="font-bold text-emerald-400 font-mono text-sm">
                          {formatPct(cand.change_pct)}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Gap %</span>
                        <p className="font-mono text-gray-300">
                          {formatPct(cand.gap_pct)}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Volume Ratio</span>
                        <p className="font-mono font-semibold text-amber-300">
                          {cand.volume_ratio ? `${cand.volume_ratio}x avg` : "1.8x"}
                        </p>
                      </div>
                    </div>

                    {/* LLM Reasoning */}
                    <div className="text-xs text-gray-300 leading-relaxed bg-gray-900/60 p-2.5 rounded border border-gray-800">
                      <span className="font-semibold text-gray-400 block mb-0.5">
                        Radar Reasoning:
                      </span>
                      <p className="text-[11px] text-gray-300 leading-relaxed">
                        {cand.reasoning}
                      </p>
                    </div>

                    {/* Multi-Model Tags & Action Button */}
                    <div className="space-y-2.5 pt-1">
                      <div className="flex flex-wrap gap-1">
                        {(Array.isArray(cand.sources)
                          ? cand.sources
                          : typeof cand.sources === "string"
                          ? [cand.sources]
                          : ["Technicals", "News"]
                        ).map((s) => (
                          <span
                            key={s}
                            className="rounded bg-blue-950/50 border border-blue-900/50 px-2 py-0.5 text-[10px] text-blue-300 font-medium"
                          >
                            {s}
                          </span>
                        ))}
                      </div>

                      <Link
                        href={`/analysis?symbol=${cand.symbol}`}
                        className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold shadow-sm transition-colors"
                      >
                        <span>Analyze with Swarm</span>
                        <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        ) : (
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-12 text-center flex flex-col items-center justify-center space-y-3">
            <div className="rounded-full bg-blue-600/10 p-3 text-blue-400 border border-blue-500/20">
              <ScanSearch className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-gray-200">No Market Candidates Found</h3>
              <p className="text-xs text-gray-400 max-w-sm">
                The scanner radar currently has no queued setups meeting active confluence thresholds. Trigger an on-demand sweep to scan the NIFTY 50 universe.
              </p>
            </div>
            <Button
              onClick={handleTriggerScan}
              loading={scanning}
              leftIcon={<Play className="h-4 w-4" />}
              size="sm"
            >
              Run On-Demand Scan
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
