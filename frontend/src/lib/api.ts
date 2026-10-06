/**
 * SkopaqTrader Typed API Client
 * Clean, modular, robust HTTP client connecting to FastAPI backend routers.
 * Matching contracts defined in PROJECT.md.
 */

import type {
  SystemStatus,
  SystemConfig,
  LLMModelMapping,
  StrategyVersionRecord,
  HealingEventRecord,
  PortfolioSnapshot,
  PositionRecord,
  ScannerStatus,
  ScannerCandidate,
  StartAnalysisRequest,
  StartAnalysisResponse,
  AnalysisJobDetail,
  TradeRecord,
  TradesListResponse,
  TradeSummaryStats,
  TradeFilterParams,
  MemoryRoleResponse,
  MemoryQueryParams,
  MemoryDocument,
  TradeReflectionRecord,
  PerformanceMetrics,
  DailySnapshot,
  ModelAccuracy,
  StrategyLearningCurve,
  SafetyRule,
  SafetySimulationRequest,
  SafetyResult,
  SafetyStatus,
  ChatMessage,
  ChatResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const DEFAULT_BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  timeoutMs?: number;
}

/**
 * Core JSON fetcher with typed return, query serialization, and robust error handling.
 */
async function request<T>(
  endpoint: string,
  options?: RequestOptions
): Promise<T> {
  const backendUrl =
    typeof window !== "undefined"
      ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"
      : DEFAULT_BACKEND_URL;

  let url = `${backendUrl.replace(/\/$/, "")}${endpoint}`;

  if (options?.params) {
    const searchParams = new URLSearchParams();
    Object.entries(options.params).forEach(([key, val]) => {
      if (val !== undefined && val !== null && val !== "") {
        searchParams.append(key, String(val));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const { params: _params, timeoutMs, ...fetchOptions } = options || {};

  const effectiveTimeout = timeoutMs ?? 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), effectiveTimeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: fetchOptions.signal || controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(fetchOptions?.headers || {}),
      },
    });

    if (!response.ok) {
      let errorDetail = `Request failed with status ${response.status}`;
      let body: unknown = null;
      try {
        body = await response.json();
        if (body && typeof body === "object") {
          const detail = (body as Record<string, unknown>).detail || (body as Record<string, unknown>).message;
          if (typeof detail === "string") {
            errorDetail = detail;
          } else if (Array.isArray(detail)) {
            errorDetail = detail.map((d: Record<string, unknown>) => d.msg || JSON.stringify(d)).join(", ");
          }
        }
      } catch {
        // Fallback to text
        try {
          const text = await response.text();
          if (text) errorDetail = text;
        } catch {
          // ignore
        }
      }
      throw new ApiError(response.status, errorDetail, body);
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return (await response.json()) as T;
  } catch (err: unknown) {
    if (err instanceof ApiError) {
      throw err;
    }
    const message = err instanceof Error ? err.message : "Network error";
    throw new ApiError(0, message);
  } finally {
    clearTimeout(timeoutId);
  }
}

// ==========================================
// 1. System & Health API
// ==========================================
export const systemApi = {
  getStatus: () => request<SystemStatus>("/api/status"),
  getConfig: () => request<SystemConfig>("/api/system/config"),
  getModels: () =>
    request<any>("/api/system/models").then((res) => {
      if (Array.isArray(res)) return res as LLMModelMapping[];
      if (res && Array.isArray(res.roles)) {
        return res.roles.map((r: any): LLMModelMapping => ({
          role: r.name || r.role,
          model: r.primary_model || "unknown",
          provider: r.primary_provider || "unknown",
          purpose: `Tier: ${r.status || "active"} • Primary: ${r.primary_model} • Fallback: ${r.fallback_model || "none"}`,
        }));
      }
      return [];
    }),
  getStrategies: () =>
    request<StrategyVersionRecord[] | { history?: StrategyVersionRecord[]; active_strategy?: StrategyVersionRecord; dna_yaml?: string }>(
      "/api/system/strategies"
    ).then((res) => {
      if (Array.isArray(res)) return res;
      if (res && Array.isArray(res.history)) return res.history;
      if (res && res.active_strategy) return [res.active_strategy];
      return [];
    }),
  getDna: () =>
    request<{ active_version: string; history: StrategyVersionRecord[]; yaml: string }>(
      "/api/system/dna"
    ).catch(() =>
      // Fallback to strategies endpoint if /dna is unmounted
      systemApi.getStrategies().then((strategies) => ({
        active_version: strategies.find((s) => s.is_active)?.version || "v1.0.0",
        history: strategies,
        yaml: "# SkopaqTrader Strategy DNA\nversion: 1.0.0\nrisk_mode: balanced\nmax_portfolio_risk_pct: 2.0\n",
      }))
    ),
  getHealingEvents: () =>
    request<HealingEventRecord[] | { events?: HealingEventRecord[]; unresolved_count?: number }>(
      "/api/system/healing"
    ).then((res) => {
      if (Array.isArray(res)) return res;
      if (res && Array.isArray(res.events)) return res.events;
      return [];
    }),
  logHealingEvent: (payload: Partial<HealingEventRecord>) =>
    request<{ success: boolean; event: HealingEventRecord }>("/api/system/healing/log", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

// ==========================================
// 2. Portfolio API & Normalizer
// ==========================================
export function normalizePositionRecord(raw: any): PositionRecord {
  if (!raw || typeof raw !== "object") {
    return {
      symbol: "UNKNOWN",
      quantity: 0,
      side: "BUY",
      avg_price: 0,
      ltp: 0,
      current_price: 0,
      current_value: 0,
      unrealized_pnl: 0,
      unrealized_pnl_pct: 0,
    };
  }
  const qty = Number(raw.quantity ?? raw.net_qty ?? 0);
  const avgPrice = Number(raw.avg_price ?? raw.average_price ?? 0);
  const ltp = Number(raw.ltp ?? raw.last_price ?? raw.current_price ?? avgPrice);
  const side = raw.side || (qty >= 0 ? "BUY" : "SELL");
  const pnl = raw.unrealized_pnl !== undefined
    ? Number(raw.unrealized_pnl)
    : (raw.pnl !== undefined ? Number(raw.pnl) : (ltp - avgPrice) * qty);
  const currentValue = Number(raw.current_value ?? (ltp * Math.abs(qty)));
  const costBasis = avgPrice * Math.abs(qty);
  const pnlPct = raw.unrealized_pnl_pct !== undefined
    ? Number(raw.unrealized_pnl_pct)
    : (costBasis > 0 ? (pnl / costBasis) * 100 : 0);

  return {
    symbol: String(raw.symbol || "").toUpperCase(),
    quantity: Math.abs(qty),
    side,
    avg_price: avgPrice,
    ltp,
    current_price: ltp,
    current_value: currentValue,
    unrealized_pnl: pnl,
    unrealized_pnl_pct: pnlPct,
    stop_loss: raw.stop_loss !== undefined && raw.stop_loss !== null ? Number(raw.stop_loss) : null,
    target: raw.target !== undefined && raw.target !== null ? Number(raw.target) : null,
    entry_time: raw.entry_time || raw.created_at || new Date().toISOString(),
    sector: raw.sector || "General",
  };
}

export const portfolioApi = {
  getSnapshot: () =>
    request<any>("/api/portfolio").then((res): PortfolioSnapshot => {
      const rawPositions = Array.isArray(res?.positions) ? res.positions : [];
      const positions = rawPositions.map(normalizePositionRecord);
      const openOrders = Array.isArray(res?.open_orders) ? res.open_orders : [];
      return {
        total_value: Number(res?.total_value ?? 1000000),
        cash: Number(res?.cash ?? 1000000),
        positions_value: Number(res?.positions_value ?? 0),
        day_pnl: Number(res?.day_pnl ?? 0),
        day_pnl_pct: Number(res?.day_pnl_pct ?? 0),
        margin_utilized: Number(res?.margin_utilized ?? 0),
        positions,
        open_orders: openOrders,
        holdings: Array.isArray(res?.holdings) ? res.holdings : [],
      };
    }),
};

// ==========================================
// 3. Scanner API
// ==========================================
export const scannerApi = {
  getStatus: () => request<ScannerStatus>("/api/scanner/status"),
  getCandidates: () =>
    request<ScannerCandidate[] | { candidates: ScannerCandidate[] }>("/api/scanner/candidates").then((res) =>
      Array.isArray(res) ? res : res.candidates || []
    ),
  triggerScan: () =>
    request<{ success: boolean; triggered_at: string; candidates_found?: number }>("/api/scanner/scan", {
      method: "POST",
    }),
};

// ==========================================
// 4. Multi-Agent Analysis API
// ==========================================
export const analysisApi = {
  startAnalysis: (params: StartAnalysisRequest) =>
    request<StartAnalysisResponse>("/api/analysis", {
      method: "POST",
      body: JSON.stringify(params),
    }).catch((err) => {
      // Compatibility with alternate route /api/analysis/start
      if (err.status === 404) {
        return request<StartAnalysisResponse>("/api/analysis/start", {
          method: "POST",
          body: JSON.stringify(params),
        });
      }
      throw err;
    }),
  getJob: (jobId: string) => request<AnalysisJobDetail>(`/api/analysis/${jobId}`),
  validateSymbol: (symbol: string, assetClass: string = "equity") =>
    request<{
      valid: boolean;
      symbol: string;
      exchange: string;
      company_name?: string | null;
      source: string;
      error?: string | null;
    }>("/api/analysis/validate", {
      params: { symbol, asset_class: assetClass },
    }),
  getStreamUrl: (jobId: string) => {
    const backendUrl =
      typeof window !== "undefined"
        ? process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"
        : DEFAULT_BACKEND_URL;
    return `${backendUrl.replace(/\/$/, "")}/api/analysis/${jobId}/stream`;
  },
};

// ==========================================
// 5. Trades History API & Normalizer
// ==========================================
export function normalizeTradeRecord(raw: any): TradeRecord {
  if (!raw || typeof raw !== "object") {
    return {
      trade_id: `trd_${Date.now()}`,
      symbol: "UNKNOWN",
      side: "BUY",
      quantity: 0,
      entry_price: 0,
      status: "closed",
      mode: "paper",
      entry_time: new Date().toISOString(),
    };
  }
  const id = raw.trade_id || raw.id || `trd_${Date.now()}`;
  const entryPrice = Number(raw.entry_price ?? raw.price ?? raw.fill_price ?? 0);
  const exitPrice = raw.exit_price !== undefined && raw.exit_price !== null
    ? Number(raw.exit_price)
    : (raw.fill_price && (raw.side === "SELL" || raw.status === "closed" || raw.status === "FILLED") ? Number(raw.fill_price) : null);
  const realizedPnl = raw.realized_pnl !== undefined && raw.realized_pnl !== null
    ? Number(raw.realized_pnl)
    : (raw.pnl !== undefined && raw.pnl !== null ? Number(raw.pnl) : null);
  const qty = Number(raw.quantity ?? 0);
  const costBasis = entryPrice * qty;
  const realizedPnlPct = raw.realized_pnl_pct !== undefined && raw.realized_pnl_pct !== null
    ? Number(raw.realized_pnl_pct)
    : (realizedPnl !== null && costBasis > 0 ? (realizedPnl / costBasis) * 100 : null);

  const rawStatus = String(raw.status || "open").toLowerCase();
  const status = (rawStatus === "filled" || rawStatus === "completed" || rawStatus === "closed") ? "closed" : rawStatus;
  const isPaper = raw.mode === "paper" || raw.is_paper === true || raw.is_paper === "true" || raw.is_paper === undefined;
  const mode = isPaper ? "paper" : "live";

  return {
    ...raw,
    id: String(raw.id || id),
    trade_id: String(id),
    symbol: String(raw.symbol || "").toUpperCase(),
    side: String(raw.side || "BUY").toUpperCase(),
    quantity: qty,
    entry_price: entryPrice,
    exit_price: exitPrice,
    fill_price: raw.fill_price ? Number(raw.fill_price) : entryPrice,
    realized_pnl: realizedPnl,
    realized_pnl_pct: realizedPnlPct,
    status,
    mode,
    strategy: raw.strategy || raw.strategy_version || "Momentum Breakout",
    entry_time: raw.entry_time || raw.created_at || new Date().toISOString(),
    exit_time: raw.exit_time || raw.closed_at || null,
    entry_rationale: raw.entry_rationale || raw.entry_reason || "",
    exit_rationale: raw.exit_rationale || raw.exit_reason || "",
    signals: raw.signals || raw.model_signals || {},
    model_predictions: Array.isArray(raw.model_predictions) ? raw.model_predictions : [],
    reflection: raw.reflection || null,
    macro_context: raw.macro_context || {
      nifty_level: raw.nifty_level ? Number(raw.nifty_level) : undefined,
      india_vix: raw.india_vix ? Number(raw.india_vix) : undefined,
      brokerage: raw.brokerage ? Number(raw.brokerage) : undefined,
      slippage: raw.slippage ? Number(raw.slippage) : undefined,
    },
  };
}

export const tradesApi = {
  getTrades: (params?: TradeFilterParams) =>
    request<TradesListResponse | TradeRecord[]>("/api/trades", {
      params: {
        limit: params?.limit,
        offset: params?.offset,
        status: params?.status,
        symbol: params?.symbol,
        strategy: params?.strategy,
        side: params?.side,
        is_paper: params?.is_paper,
        is_today: params?.is_today,
      },
    }).then((res) => {
      let rawList: any[] = [];
      let total = 0;
      if (Array.isArray(res)) {
        rawList = res;
        total = res.length;
      } else if (res && typeof res === "object") {
        rawList = Array.isArray(res.trades) ? res.trades : [];
        total = res.total !== undefined ? res.total : rawList.length;
      }
      return {
        trades: rawList.map(normalizeTradeRecord),
        total,
      };
    }),
  getTradeDetail: (tradeId: string) =>
    request<any>(`/api/trades/${tradeId}`).then(normalizeTradeRecord),
  getSummaryStats: () =>
    request<TradeSummaryStats>("/api/trades/summary/stats").catch((err) => {
      // Fallback to /api/trades/summary if /stats is 404
      if (err.status === 404) {
        return request<TradeSummaryStats>("/api/trades/summary");
      }
      throw err;
    }),
};

// ==========================================
// 6. Memory API
// ==========================================
export const memoryApi = {
  getRoles: () =>
    request<any>("/api/memory/roles").then((res) => {
      if (Array.isArray(res)) return res;
      if (res && Array.isArray(res.roles)) return res.roles;
      return [];
    }),
  getRoleMemories: (roleName: string) => request<MemoryRoleResponse>(`/api/memory/role/${roleName}`),
  queryMemory: (params: MemoryQueryParams) =>
    request<any>("/api/memory/query", {
      method: "POST",
      body: JSON.stringify(params),
    }).then((res) => {
      if (Array.isArray(res)) return res as MemoryDocument[];
      if (res && Array.isArray(res.results)) return res.results as MemoryDocument[];
      return [];
    }),
  getReflections: (symbol?: string, limit?: number) =>
    request<any>("/api/memory/reflections", {
      params: { symbol, limit },
    }).then((res) => {
      if (Array.isArray(res)) return res as TradeReflectionRecord[];
      if (res && Array.isArray(res.reflections)) return res.reflections as TradeReflectionRecord[];
      return [];
    }),
};

// ==========================================
// 7. Performance API
// ==========================================
export const performanceApi = {
  getMetrics: () => request<PerformanceMetrics>("/api/performance/metrics"),
  getDailySnapshots: () =>
    request<DailySnapshot[] | { snapshots?: DailySnapshot[] }>("/api/performance/daily-snapshots")
      .catch((err) => {
        if (err.status === 404) {
          return request<DailySnapshot[] | { snapshots?: DailySnapshot[] }>("/api/performance/snapshots");
        }
        throw err;
      })
      .then((res) => {
        if (Array.isArray(res)) return res;
        if (res && Array.isArray(res.snapshots)) return res.snapshots;
        return [];
      }),
  getModelAccuracy: () =>
    request<ModelAccuracy[] | { models?: ModelAccuracy[] }>("/api/performance/models")
      .catch((err) => {
        if (err.status === 404) {
          return request<ModelAccuracy[] | { models?: ModelAccuracy[] }>("/api/performance/model-accuracy");
        }
        throw err;
      })
      .then((res) => {
        if (Array.isArray(res)) return res;
        if (res && Array.isArray(res.models)) return res.models;
        return [];
      }),
  getLearningCurve: () => request<StrategyLearningCurve[]>("/api/performance/learning"),
};

// ==========================================
// 8. Safety & Simulation API
// ==========================================
export const safetyApi = {
  getRules: () => request<SafetyRule[] | Record<string, unknown>>("/api/safety/rules"),
  simulate: (payload: SafetySimulationRequest) =>
    request<SafetyResult>("/api/safety/simulate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getStatus: () => request<SafetyStatus>("/api/safety/status"),
};

// ==========================================
// 9. Interactive Chat API
// ==========================================
export const chatApi = {
  sendMessage: (message: string, sessionId?: string) =>
    request<ChatResponse>("/api/chat/message", {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
      timeoutMs: 45000,
    }),
  callTool: (toolName: string, args: Record<string, unknown>, sessionId?: string) =>
    request<ChatResponse>("/api/chat/tool", {
      method: "POST",
      body: JSON.stringify({ tool: toolName, args, session_id: sessionId }),
      timeoutMs: 45000,
    }),
};

/**
 * Unified root API client export
 */
export const api = {
  system: systemApi,
  portfolio: portfolioApi,
  scanner: scannerApi,
  analysis: analysisApi,
  trades: tradesApi,
  memory: memoryApi,
  performance: performanceApi,
  safety: safetyApi,
  chat: chatApi,
};

export default api;
