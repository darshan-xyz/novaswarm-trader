"use client";

/**
 * Custom SSE Streaming Hook for Multi-Agent Graph Analysis.
 * Features:
 * - Late joiner support: Backfills initial state from GET /api/analysis/{job_id} snapshot.
 * - Auto-reconnect: Exponential backoff with jitter on dropped connections.
 * - Message buffering: Safely queues rapid events and accumulates markdown chunks per agent.
 * - Clean lifecycle: Tears down EventSource on unmount, terminal states, or jobId change.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import type {
  AgentStatusEvent,
  EventLogEntry,
  DecisionCardData,
  AnalysisStreamEvent,
} from "./types";
import { analysisApi } from "./api";

export type StreamConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "completed"
  | "failed"
  | "error";

export interface UseAgentStreamOptions {
  autoReconnect?: boolean;
  maxReconnectAttempts?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  onEvent?: (event: AnalysisStreamEvent) => void;
  onDecision?: (decision: DecisionCardData) => void;
  onComplete?: () => void;
  onError?: (err: Error) => void;
}

export interface UseAgentStreamResult {
  connectionStatus: StreamConnectionStatus;
  isConnected: boolean;
  isCompleted: boolean;
  error: string | null;
  agentStatuses: Record<string, AgentStatusEvent>;
  reports: Record<string, string>; // agent_id -> accumulated markdown report
  logs: EventLogEntry[];
  decision: DecisionCardData | null;
  finalVerdict: string | null;
  confidence: number | null;
  durationSeconds: number | null;
  bufferedEventsCount: number;
  reconnect: () => void;
  disconnect: () => void;
  reset: () => void;
}

export function useAgentStream(
  jobId: string | null,
  options: UseAgentStreamOptions = {}
): UseAgentStreamResult {
  const {
    autoReconnect = true,
    maxReconnectAttempts = 5,
    initialBackoffMs = 1000,
    maxBackoffMs = 15000,
    onEvent,
    onDecision,
    onComplete,
    onError,
  } = options;

  const [connectionStatus, setConnectionStatus] =
    useState<StreamConnectionStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<
    Record<string, AgentStatusEvent>
  >({});
  const [reports, setReports] = useState<Record<string, string>>({});
  const [logs, setLogs] = useState<EventLogEntry[]>([]);
  const [decision, setDecision] = useState<DecisionCardData | null>(null);
  const [finalVerdict, setFinalVerdict] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [durationSeconds, setDurationSeconds] = useState<number | null>(null);
  const [bufferedEventsCount, setBufferedEventsCount] = useState<number>(0);

  // Mutable refs to prevent stale closure issues and manage lifecycle
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isTerminalRef = useRef<boolean>(false);
  const eventBufferRef = useRef<AnalysisStreamEvent[]>([]);
  const isProcessingBufferRef = useRef<boolean>(false);

  // Store latest callbacks
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const onDecisionRef = useRef(onDecision);
  onDecisionRef.current = onDecision;
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // Cleanup active connection and timers
  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  // Reset full state
  const reset = useCallback(() => {
    cleanup();
    isTerminalRef.current = false;
    reconnectAttemptsRef.current = 0;
    eventBufferRef.current = [];
    setConnectionStatus("idle");
    setError(null);
    setAgentStatuses({});
    setReports({});
    setLogs([]);
    setDecision(null);
    setFinalVerdict(null);
    setConfidence(null);
    setDurationSeconds(null);
    setBufferedEventsCount(0);
  }, [cleanup]);

  // Buffer drain processor: consumes queued events in batches
  const processBuffer = useCallback(() => {
    if (isProcessingBufferRef.current || eventBufferRef.current.length === 0) {
      return;
    }

    isProcessingBufferRef.current = true;
    const batch = eventBufferRef.current.splice(0, eventBufferRef.current.length);
    setBufferedEventsCount(eventBufferRef.current.length);

    batch.forEach((event) => {
      try {
        onEventRef.current?.(event);
      } catch (e) {
        console.error("Error in onEvent callback:", e);
      }

      switch (event.type) {
        case "agent_status": {
          const statusData = event.data;
          setAgentStatuses((prev) => ({
            ...prev,
            [statusData.agent_id]: statusData,
          }));
          break;
        }

        case "agent_chunk":
        case "report_chunk": {
          const { agent_id, chunk } = event.data;
          setReports((prev) => ({
            ...prev,
            [agent_id]: (prev[agent_id] || "") + chunk,
          }));
          break;
        }

        case "agent_report": {
          const { agent_id, report_markdown } = event.data;
          setReports((prev) => ({
            ...prev,
            [agent_id]: report_markdown,
          }));
          break;
        }

        case "event_log": {
          const logEntry = event.data;
          setLogs((prev) => [...prev, logEntry]);
          break;
        }

        case "tool_call": {
          const tc = event.data;
          setLogs((prev) => [
            ...prev,
            {
              level: "INFO",
              message: `Agent ${tc.agent_id} invoked tool: ${tc.tool_name}`,
              timestamp: tc.timestamp,
              tool_call: tc,
            },
          ]);
          break;
        }

        case "decision_card": {
          const dec = event.data;
          setDecision(dec);
          onDecisionRef.current?.(dec);
          break;
        }

        case "job_completed":
        case "done": {
          isTerminalRef.current = true;
          setConnectionStatus("completed");
          const data = event.data;
          if (data.final_verdict) setFinalVerdict(data.final_verdict);
          if (data.confidence !== undefined) setConfidence(data.confidence);
          if (data.duration_seconds !== undefined) setDurationSeconds(data.duration_seconds);
          onCompleteRef.current?.();
          cleanup();
          break;
        }

        case "job_failed":
        case "error": {
          isTerminalRef.current = true;
          setConnectionStatus("failed");
          const data = event.data;
          setError(data.error || (data as any).message || "Analysis job failed");
          cleanup();
          break;
        }

        case "keepalive":
        case "job_started":
        default:
          break;
      }
    });

    isProcessingBufferRef.current = false;
    if (eventBufferRef.current.length > 0) {
      setTimeout(processBuffer, 10);
    }
  }, [cleanup]);

  const enqueueEvent = useCallback(
    (event: AnalysisStreamEvent) => {
      eventBufferRef.current.push(event);
      setBufferedEventsCount(eventBufferRef.current.length);
      processBuffer();
    },
    [processBuffer]
  );

  // Late joiner snapshot loader: backfill existing state if job already started/finished
  const fetchSnapshot = useCallback(
    async (id: string) => {
      try {
        const job = await analysisApi.getJob(id);
        if (job) {
          if (job.agent_statuses) {
            setAgentStatuses((prev) => ({ ...job.agent_statuses, ...prev }));
          }
          if (job.reports) {
            setReports((prev) => ({ ...job.reports, ...prev }));
          }
          if (job.logs && job.logs.length > 0) {
            setLogs((prev) => {
              const existingTimes = new Set(prev.map((l) => `${l.timestamp}_${l.message}`));
              const newLogs = job.logs.filter(
                (l) => !existingTimes.has(`${l.timestamp}_${l.message}`)
              );
              return [...prev, ...newLogs];
            });
          }
          if (job.decision) {
            setDecision(job.decision);
          }
          if (job.status === "completed") {
            isTerminalRef.current = true;
            setConnectionStatus("completed");
            if (job.decision) {
              setFinalVerdict(job.decision.verdict);
              setConfidence(job.decision.confidence);
            }
          } else if (job.status === "failed") {
            isTerminalRef.current = true;
            setConnectionStatus("failed");
            setError(job.error || "Job failed");
          }
        }
      } catch (err) {
        // Non-fatal: if snapshot fails (e.g. backend still starting up), stream will still connect
        console.warn("Could not fetch initial analysis job snapshot:", err);
      }
    },
    []
  );

  // Establish SSE Connection
  const connect = useCallback(
    (id: string) => {
      if (isTerminalRef.current) return;
      cleanup();

      const streamUrl = analysisApi.getStreamUrl(id);
      setConnectionStatus((prev) =>
        reconnectAttemptsRef.current > 0 ? "reconnecting" : "connecting"
      );

      try {
        const es = new EventSource(streamUrl);
        eventSourceRef.current = es;

        es.onopen = () => {
          reconnectAttemptsRef.current = 0;
          setConnectionStatus("connected");
          setError(null);
        };

        // Listen for standard message / typed events
        es.onmessage = (event) => {
          if (!event.data) return;
          try {
            const parsed = JSON.parse(event.data);
            // Handle both { type: "...", data: ... } and direct event envelopes
            if (parsed.type) {
              enqueueEvent(parsed);
            } else if (parsed.verdict && parsed.confidence !== undefined) {
              enqueueEvent({ type: "decision_card", data: parsed });
            } else if (parsed.agent_id && parsed.chunk) {
              enqueueEvent({ type: "agent_chunk", data: parsed });
            } else if (parsed.agent_id && parsed.status) {
              enqueueEvent({ type: "agent_status", data: parsed });
            } else if (parsed.message && parsed.level) {
              enqueueEvent({ type: "event_log", data: parsed });
            }
          } catch (e) {
            // Raw text log or keepalive
            if (event.data.includes("keepalive") || event.data.trim() === "ping") {
              return;
            }
            enqueueEvent({
              type: "event_log",
              data: {
                level: "INFO",
                message: event.data,
                timestamp: new Date().toISOString(),
              },
            });
          }
        };

        // Handle SSE custom event listeners matching backend emit names
        const customEvents = [
          "job_started",
          "agent_status",
          "tool_call",
          "agent_chunk",
          "report_chunk",
          "agent_report",
          "event_log",
          "decision_card",
          "job_completed",
          "done",
          "job_failed",
          "error",
        ];

        customEvents.forEach((evtName) => {
          es.addEventListener(evtName, (event: MessageEvent) => {
            if (!event.data) return;
            try {
              const data = JSON.parse(event.data);
              enqueueEvent({ type: evtName as any, data });
            } catch {
              enqueueEvent({
                type: "event_log",
                data: {
                  level: "INFO",
                  message: `${evtName}: ${event.data}`,
                  timestamp: new Date().toISOString(),
                },
              });
            }
          });
        });

        es.onerror = () => {
          cleanup();
          if (isTerminalRef.current) return;

          if (
            autoReconnect &&
            reconnectAttemptsRef.current < maxReconnectAttempts
          ) {
            reconnectAttemptsRef.current += 1;
            // Exponential backoff with jitter
            const backoff = Math.min(
              initialBackoffMs * Math.pow(1.5, reconnectAttemptsRef.current) +
                Math.random() * 500,
              maxBackoffMs
            );
            setConnectionStatus("reconnecting");
            reconnectTimeoutRef.current = setTimeout(() => {
              connect(id);
            }, backoff);
          } else {
            setConnectionStatus("error");
            const errMsg = "Connection to analysis event stream lost.";
            setError(errMsg);
            onErrorRef.current?.(new Error(errMsg));
          }
        };
      } catch (err: unknown) {
        const errorInstance =
          err instanceof Error ? err : new Error(String(err));
        setConnectionStatus("error");
        setError(errorInstance.message);
        onErrorRef.current?.(errorInstance);
      }
    },
    [
      cleanup,
      autoReconnect,
      maxReconnectAttempts,
      initialBackoffMs,
      maxBackoffMs,
      enqueueEvent,
    ]
  );

  // Trigger connection when jobId changes
  useEffect(() => {
    if (!jobId) {
      reset();
      return;
    }

    reset();
    // 1. Fetch initial snapshot for late joiners
    fetchSnapshot(jobId).then(() => {
      // 2. If already completed from snapshot, don't open stream
      if (!isTerminalRef.current) {
        connect(jobId);
      }
    });

    return () => {
      cleanup();
    };
  }, [jobId, connect, fetchSnapshot, reset, cleanup]);

  const reconnect = useCallback(() => {
    if (jobId) {
      isTerminalRef.current = false;
      reconnectAttemptsRef.current = 0;
      connect(jobId);
    }
  }, [jobId, connect]);

  const disconnect = useCallback(() => {
    cleanup();
    setConnectionStatus("idle");
  }, [cleanup]);

  return {
    connectionStatus,
    isConnected: connectionStatus === "connected",
    isCompleted: connectionStatus === "completed",
    error,
    agentStatuses,
    reports,
    logs,
    decision,
    finalVerdict,
    confidence,
    durationSeconds,
    bufferedEventsCount,
    reconnect,
    disconnect,
    reset,
  };
}

export default useAgentStream;
