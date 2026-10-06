/**
 * Comprehensive TypeScript domain definitions for SkopaqTrader Web UI & API client.
 * Matching specifications from PROJECT.md and backend routers.
 */

// ==========================================
// 1. System & Health Models
// ==========================================

export interface BrokerStatus {
  name: string;
  token_valid: boolean;
  token_remaining: string | null;
  token_warning: string | null;
}

export interface ServicesStatus {
  supabase: boolean;
  redis: boolean;
  llms: Record<string, boolean>;
}

export interface SystemStatus {
  version: string;
  mode: "paper" | "live" | string;
  broker: BrokerStatus;
  services: ServicesStatus;
}

export interface SystemConfig {
  broker_mode: "paper" | "live" | string;
  environment: string;
  active_models: Record<string, string>;
  scanner_intervals?: {
    market_hours_sec: number;
    off_hours_sec: number;
  };
  risk_limits?: {
    max_drawdown_pct: number;
    daily_loss_limit_inr: number;
    max_position_size_inr: number;
    max_sector_concentration_pct: number;
  };
  [key: string]: unknown;
}

export interface LLMModelMapping {
  role: string;
  model: string;
  provider: string;
  purpose: string;
}

export interface StrategyVersionRecord {
  version: string;
  name: string;
  description: string;
  is_active: boolean;
  sharpe?: number;
  win_rate?: number;
  max_drawdown?: number;
  created_at: string;
  parameters?: Record<string, unknown>;
  dna_yaml?: string;
}

export interface HealingEventRecord {
  id?: string;
  timestamp: string;
  component: string;
  event_type: string;
  action_taken: string;
  status: "resolved" | "in_progress" | "failed" | string;
  details?: Record<string, unknown> | string;
}

// ==========================================
// 2. Portfolio & Orders Models
// ==========================================

export interface PositionRecord {
  symbol: string;
  quantity: number;
  side: "BUY" | "SELL" | string;
  avg_price: number;
  current_price?: number;
  ltp?: number;
  current_value?: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  stop_loss?: number | null;
  target?: number | null;
  entry_time?: string;
  sector?: string;
}

export interface OrderRecord {
  order_id: string;
  symbol: string;
  side: "BUY" | "SELL" | string;
  quantity: number;
  price: number;
  order_type: "MARKET" | "LIMIT" | string;
  status: "FILLED" | "PENDING" | "REJECTED" | "CANCELLED" | string;
  created_at: string;
  trigger_source?: string;
  rejection_reason?: string;
}

export interface HoldingRecord {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  current_value: number;
  total_pnl: number;
  total_pnl_pct: number;
  day_change_pct: number;
  sector?: string;
}

export interface PortfolioSnapshot {
  total_value: number;
  cash: number;
  positions_value: number;
  day_pnl: number;
  day_pnl_pct?: number;
  margin_utilized?: number;
  positions: PositionRecord[];
  open_orders: OrderRecord[];
  holdings?: HoldingRecord[];
}

// ==========================================
// 3. Market Scanner Models
// ==========================================

export interface ScannerStatus {
  running: boolean;
  cycle_count: number;
  last_cycle_at: string | null;
  watchlist_size: number;
  queue_size: number;
  screeners: string[] | { active?: string[]; count?: number };
}

export interface ScannerCandidate {
  symbol: string;
  exchange: string;
  urgency: "HIGH" | "NORMAL" | "LOW" | string;
  sources: string[];
  ltp: number;
  change_pct: number;
  gap_pct: number;
  volume_ratio: number;
  reasoning: string;
  score?: number;
  timestamp?: string;
}

export interface ScannerResponse {
  status: ScannerStatus;
  candidates: ScannerCandidate[];
}

// ==========================================
// 4. Multi-Agent Analysis Models & SSE
// ==========================================

export interface StartAnalysisRequest {
  symbol: string;
  urgency?: "low" | "medium" | "high";
  lookback_days?: number;
  trade_date?: string;
}

export interface StartAnalysisResponse {
  job_id: string;
  symbol: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
}

export interface DecisionCardData {
  verdict: "BUY" | "SELL" | "HOLD";
  confidence: number; // 0-100
  position_size: number; // shares
  position_size_inr?: number;
  entry_price: number;
  stop_loss: number;
  target: number;
  risk_reward_ratio: number;
  reasoning: string;
  timestamp: string;
}

export interface AgentStatusEvent {
  agent_id: string;
  team: string;
  status: "pending" | "running" | "completed" | "failed";
  latency_ms?: number;
  timestamp: string;
}

export interface ToolCallEvent {
  agent_id: string;
  tool_name: string;
  tool_args: Record<string, unknown>;
  tool_result?: unknown;
  timestamp: string;
}

export interface AgentChunkEvent {
  agent_id: string;
  chunk: string;
  timestamp: string;
}

export interface AgentReportEvent {
  agent_id: string;
  team: string;
  report_markdown: string;
  timestamp: string;
}

export interface EventLogEntry {
  level: "INFO" | "WARNING" | "ERROR";
  message: string;
  timestamp: string;
  tool_call?: ToolCallEvent;
}

export interface JobCompletedEvent {
  job_id: string;
  final_verdict: string;
  confidence: number;
  duration_seconds: number;
  timestamp: string;
}

export interface JobFailedEvent {
  job_id: string;
  error: string;
  timestamp: string;
}

export interface AnalysisJobDetail {
  job_id: string;
  symbol: string;
  urgency: string;
  lookback_days: number;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  completed_at?: string | null;
  agent_statuses: Record<string, AgentStatusEvent>;
  reports: Record<string, string>;
  logs: EventLogEntry[];
  decision?: DecisionCardData | null;
  error?: string | null;
}

export type AnalysisStreamEvent =
  | { type: "job_started"; data: { job_id: string; symbol: string; timestamp: string } }
  | { type: "agent_status"; data: AgentStatusEvent }
  | { type: "tool_call"; data: ToolCallEvent }
  | { type: "agent_chunk"; data: AgentChunkEvent }
  | { type: "report_chunk"; data: AgentChunkEvent }
  | { type: "agent_report"; data: AgentReportEvent }
  | { type: "event_log"; data: EventLogEntry }
  | { type: "decision_card"; data: DecisionCardData }
  | { type: "job_completed"; data: JobCompletedEvent }
  | { type: "done"; data: Partial<JobCompletedEvent> }
  | { type: "job_failed"; data: JobFailedEvent }
  | { type: "error"; data: { message?: string; error?: string } }
  | { type: "keepalive"; data: { timestamp: string } };

// ==========================================
// 5. Trades Models
// ==========================================

export interface TradeModelPrediction {
  model_name: string;
  prediction: "BUY" | "SELL" | "HOLD";
  confidence: number;
  signals?: Record<string, unknown>;
}

export interface TradeRecord {
  id?: string;
  trade_id: string;
  symbol: string;
  side: "BUY" | "SELL" | string;
  quantity: number;
  entry_price: number;
  exit_price?: number | null;
  fill_price?: number;
  realized_pnl?: number | null;
  realized_pnl_pct?: number | null;
  status: "open" | "closed" | "pending" | string;
  mode: "paper" | "live" | string;
  strategy?: string;
  entry_time: string;
  exit_time?: string | null;
  entry_rationale?: string;
  exit_rationale?: string;
  signals?: Record<string, unknown>;
  model_predictions?: TradeModelPrediction[];
  reflection?: {
    lesson: string;
    outcome_review: string;
    memory_key?: string;
  } | null;
  macro_context?: {
    nifty_level?: number;
    india_vix?: number;
    slippage?: number;
    brokerage?: number;
  };
}

export interface TradesListResponse {
  trades: TradeRecord[];
  total: number;
}

export interface TradeSummaryStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_realized_pnl: number;
  gross_profit: number;
  gross_loss: number;
  profit_factor: number;
}

export interface TradeFilterParams {
  limit?: number;
  offset?: number;
  status?: string;
  symbol?: string;
  strategy?: string;
  side?: string;
  is_paper?: boolean;
  is_today?: boolean;
}

// ==========================================
// 6. Memory Models
// ==========================================

export type MemoryRole =
  | "bull_memory"
  | "bear_memory"
  | "trader_memory"
  | "invest_judge_memory"
  | "risk_manager_memory"
  | string;

export interface MemoryDocument {
  id: string;
  role: string;
  content: string;
  score?: number;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

export interface MemoryRoleResponse {
  role: string;
  documents_count: number;
  memories: MemoryDocument[];
}

export interface MemoryQueryParams {
  role: string;
  query: string;
  top_k?: number;
}

export interface TradeReflectionRecord {
  trade_id: string;
  symbol: string;
  lesson: string;
  outcome_review: string;
  timestamp: string;
  pnl?: number;
}

// ==========================================
// 7. Performance Models
// ==========================================

export interface PerformanceMetrics {
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_pnl: number;
  profit_factor: number;
  total_trades: number;
  avg_trade_duration_days?: number;
  win_loss_ratio?: number;
  annualized_return_pct?: number;
}

export interface DailySnapshot {
  date: string;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  drawdown_pct: number;
}

export interface ModelAccuracy {
  model_name: string;
  total_predictions: number;
  accurate_predictions: number;
  accuracy_pct: number;
  avg_confidence: number;
}

export interface StrategyLearningCurve {
  generation: number;
  sharpe: number;
  win_rate: number;
  timestamp: string;
  adaptations: string[];
}

// ==========================================
// 8. Safety & Simulation Models
// ==========================================

export interface SafetyRule {
  id: string;
  name: string;
  description: string;
  threshold: number | string;
  level: "CRITICAL" | "WARNING" | "INFO";
  enabled: boolean;
}

export interface SafetySimulationRequest {
  symbol: string;
  action: "BUY" | "SELL";
  quantity: number;
  price: number;
  stop_loss?: number;
  target?: number;
}

export interface SafetyResult {
  passed: boolean;
  rejections: string[];
  warnings: string[];
  risk_pct: number;
  max_allowed_quantity: number;
}

export interface SafetyStatus {
  daily_drawdown: number;
  kill_switch_active: boolean;
  open_orders_count: number;
  orders_per_minute: number;
  active_warnings?: string[];
}

// ==========================================
// 9. Interactive Chat Models
// ==========================================

export interface ChatToolCall {
  tool_name: string;
  tool_args: Record<string, unknown>;
  tool_result?: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  tool_calls?: ChatToolCall[];
}

export interface ChatResponse {
  message: string;
  session_id: string;
  tool_calls?: ChatToolCall[];
}
