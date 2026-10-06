"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { chatApi } from "@/lib/api";
import type { ChatMessage, ChatToolCall, ChatResponse } from "@/lib/types";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
  Badge,
  Button,
  Markdown,
  Spinner,
} from "@/components/ui";
import {
  MessageSquareCode,
  Send,
  Bot,
  User,
  Wrench,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
} from "lucide-react";

interface ActionCardData {
  action: "BUY" | "SELL" | "HOLD";
  symbol: string;
  quantity: number;
  entryPrice: number;
  targetPrice: number;
  stopLossPrice: number;
  riskReward: string;
}

function extractActionCard(content: string): ActionCardData | null {
  if (content.includes("Action:") && content.includes("Symbol:")) {
    const actionMatch = content.match(/Action:\s*(BUY|SELL|HOLD)/i);
    const symbolMatch = content.match(/Symbol:\s*([A-Z0-9]+)/i);
    const qtyMatch = content.match(/Quantity:\s*(\d+)/i);
    const entryMatch = content.match(/Entry:\s*₹?([\d,.]+)/i);
    const targetMatch = content.match(/Target:\s*₹?([\d,.]+)/i);
    const slMatch = content.match(/Stop Loss:\s*₹?([\d,.]+)/i);

    if (actionMatch && symbolMatch) {
      const entry = entryMatch ? parseFloat(entryMatch[1].replace(/,/g, "")) : 3012;
      const target = targetMatch ? parseFloat(targetMatch[1].replace(/,/g, "")) : 3140;
      const sl = slMatch ? parseFloat(slMatch[1].replace(/,/g, "")) : 2950;
      const denom = Math.abs(entry - sl);
      const rr = denom > 0 ? (Math.abs(target - entry) / denom).toFixed(2) : "2.0";

      return {
        action: actionMatch[1].toUpperCase() as "BUY" | "SELL" | "HOLD",
        symbol: symbolMatch[1].toUpperCase(),
        quantity: qtyMatch ? parseInt(qtyMatch[1], 10) : 25,
        entryPrice: entry,
        targetPrice: target,
        stopLossPrice: sl,
        riskReward: `${rr}:1`,
      };
    }
  }
  return null;
}

export default function ChatPage() {
  const [sessionId, setSessionId] = useState<string>(() => `session_${Date.now()}`);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hello! I am **SkopaqTrader AI**, your autonomous Indian equities assistant. Ask me to scan momentum candidates, inspect active positions, analyze technical setups, or evaluate risk rules.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [openToolCallIdx, setOpenToolCallIdx] = useState<Record<string, boolean>>({});

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const toggleToolCall = (key: string) => {
    setOpenToolCallIdx((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const QUICK_PROMPTS = [
    "Analyze RELIANCE",
    "Portfolio Status",
    "Market Scan",
    "Safety Rules",
  ];

  const handleSend = async (textToSend?: string) => {
    const query = textToSend || input;
    if (!query.trim() || loading) return;

    const userMessage: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: "user",
      content: query.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      const res = await chatApi.sendMessage(query.trim(), sessionId);
      const normalizedToolCalls: ChatToolCall[] = Array.isArray(res.tool_calls)
        ? res.tool_calls.map((tc: any) => ({
            tool_name: tc.tool_name || tc.tool || "tool",
            tool_args: tc.tool_args || tc.args || {},
            tool_result: tc.tool_result !== undefined ? tc.tool_result : tc.result,
          }))
        : [];

      const assistantMessage: ChatMessage = {
        id: `asst_${Date.now()}`,
        role: "assistant",
        content: typeof res?.message === "string" ? res.message : String(res?.message || ""),
        timestamp: new Date().toISOString(),
        tool_calls: normalizedToolCalls,
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      const errorMsg =
        err instanceof Error
          ? err.message
          : "Failed to communicate with AI Trading Assistant backend";
      const errorMessage: ChatMessage = {
        id: `err_${Date.now()}`,
        role: "assistant",
        content: `⚠️ **Communication Error**: Unable to reach AI trading assistant (${errorMsg}). Please verify that the backend server is running and try again.`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleNewSession = () => {
    const newId = `session_${Date.now()}`;
    setSessionId(newId);
    setMessages([
      {
        id: `welcome_${Date.now()}`,
        role: "assistant",
        content:
          "Started a fresh trading assistant session. How can I assist your portfolio or market analysis today?",
        timestamp: new Date().toISOString(),
      },
    ]);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-7.5rem)] max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="rounded-lg bg-blue-600/20 p-2 text-blue-400 border border-blue-500/40">
            <MessageSquareCode className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white flex items-center gap-2">
              <span>AI Trading Assistant</span>
              <Badge variant="success" size="sm" dot>
                CONNECTED
              </Badge>
            </h2>
            <p className="text-xs text-gray-400">
              Session ID: <code className="text-blue-300 font-mono text-[11px]">{sessionId}</code>
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={handleNewSession}
          leftIcon={<RefreshCw className="h-3 w-3" />}
        >
          New Session
        </Button>
      </div>

      {/* Quick Prompts Chips */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
        <span className="text-gray-500 font-medium shrink-0 flex items-center gap-1">
          <Sparkles className="h-3.5 w-3.5 text-blue-400" />
          Quick Prompts:
        </span>
        {QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => handleSend(prompt)}
            disabled={loading}
            className="whitespace-nowrap rounded-lg border border-gray-800 bg-gray-900/90 px-3 py-1.5 text-gray-300 hover:border-blue-500/60 hover:text-white transition-colors text-xs font-medium"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Messages Thread Card */}
      <Card className="flex-1 overflow-hidden flex flex-col bg-gray-950/60 border-gray-800 shadow-inner">
        <CardContent className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((msg) => {
            const isUser = msg.role === "user";
            const actionCard = !isUser ? extractActionCard(msg.content) : null;

            return (
              <div
                key={msg.id}
                className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
              >
                {!isUser && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-900/40 border border-blue-700/60 text-blue-400">
                    <Bot className="h-4 w-4" />
                  </div>
                )}

                <div
                  className={`max-w-[85%] rounded-xl px-4 py-3.5 text-xs sm:text-sm ${
                    isUser
                      ? "bg-blue-600 text-white shadow-sm"
                      : "bg-gray-900 text-gray-200 border border-gray-800"
                  }`}
                >
                  {isUser ? (
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  ) : (
                    <Markdown content={msg.content} />
                  )}

                  {/* Trading Action Card if Action Detected */}
                  {actionCard && (
                    <div className="mt-3.5 p-3.5 rounded-xl bg-gray-950 border border-blue-800/60 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <TrendingUp className="h-4 w-4 text-emerald-400" />
                          <span className="text-xs font-bold text-white tracking-wide">
                            Trade Proposal: {actionCard.symbol}
                          </span>
                        </div>
                        <Badge
                          variant={actionCard.action === "BUY" ? "success" : "danger"}
                          size="sm"
                          className="font-bold"
                        >
                          {actionCard.action}
                        </Badge>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs bg-gray-900/80 p-2.5 rounded-lg border border-gray-800 font-mono">
                        <div>
                          <span className="text-[10px] text-gray-400 font-sans block">Quantity</span>
                          <span className="font-bold text-white">{actionCard.quantity} shares</span>
                        </div>
                        <div>
                          <span className="text-[10px] text-gray-400 font-sans block">Entry Price</span>
                          <span className="font-bold text-gray-200">₹{actionCard.entryPrice}</span>
                        </div>
                        <div>
                          <span className="text-[10px] text-gray-400 font-sans block">Stop Loss</span>
                          <span className="font-bold text-rose-400">₹{actionCard.stopLossPrice}</span>
                        </div>
                        <div>
                          <span className="text-[10px] text-gray-400 font-sans block">Target (R:R)</span>
                          <span className="font-bold text-emerald-400">
                            ₹{actionCard.targetPrice} ({actionCard.riskReward})
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Collapsible Tool Execution Cards */}
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="mt-3.5 pt-2.5 border-t border-gray-800/80 space-y-2">
                      <div className="flex items-center gap-1.5 text-[11px] font-semibold text-blue-400">
                        <Wrench className="h-3.5 w-3.5" />
                        <span>Swarm Tool Executions ({msg.tool_calls.length})</span>
                      </div>
                      {msg.tool_calls.map((tc, idx) => {
                        const callKey = `${msg.id}_tc_${idx}`;
                        const isOpen = openToolCallIdx[callKey] ?? true;

                        return (
                          <div
                            key={idx}
                            className="rounded-lg bg-gray-950 text-[11px] font-mono border border-gray-800/80 overflow-hidden"
                          >
                            <button
                              type="button"
                              onClick={() => toggleToolCall(callKey)}
                              className="w-full flex items-center justify-between px-3 py-2 bg-gray-900/60 hover:bg-gray-850 text-left transition-colors"
                            >
                              <div className="flex items-center gap-1.5">
                                {isOpen ? (
                                  <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
                                ) : (
                                  <ChevronRight className="h-3.5 w-3.5 text-gray-400" />
                                )}
                                <span className="font-bold text-amber-300">
                                  tool: {tc.tool_name}
                                </span>
                              </div>
                              <Badge variant="success" size="sm" className="text-[10px] py-0">
                                EXECUTED
                              </Badge>
                            </button>

                            {isOpen && (
                              <div className="p-3 space-y-2 bg-gray-950 text-gray-300 border-t border-gray-850">
                                <div>
                                  <span className="text-[10px] font-sans font-semibold text-gray-400 uppercase tracking-wider block mb-0.5">
                                    Arguments
                                  </span>
                                  <pre className="text-[10px] text-blue-300 bg-gray-900/90 p-2 rounded border border-gray-800 overflow-x-auto">
                                    {JSON.stringify(tc.tool_args, null, 2)}
                                  </pre>
                                </div>
                                {Boolean(tc.tool_result) && (
                                  <div>
                                    <span className="text-[10px] font-sans font-semibold text-gray-400 uppercase tracking-wider block mb-0.5">
                                      Returned Result
                                    </span>
                                    <pre className="text-[10px] text-emerald-300 bg-gray-900/90 p-2 rounded border border-gray-800 overflow-x-auto">
                                      {JSON.stringify(tc.tool_result, null, 2)}
                                    </pre>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {isUser && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-800 text-gray-300">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            );
          })}

          {loading && (
            <div className="flex items-center gap-2 text-xs text-gray-400 pl-11">
              <Spinner size="sm" />
              <span>Analyzing market context & invoking autonomous tools...</span>
            </div>
          )}

          <div ref={scrollRef} />
        </CardContent>

        {/* Input Footer */}
        <CardFooter className="p-3 border-t border-gray-800 bg-gray-900/70">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex w-full items-center gap-2"
          >
            <input
              type="text"
              placeholder="Ask about RELIANCE, trigger a market scan, or check safety rules..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              className="flex-1 rounded-lg border border-gray-800 bg-gray-950 px-3.5 py-2 text-xs sm:text-sm text-gray-100 placeholder:text-gray-500 focus:outline-none focus:border-blue-500 transition-colors"
            />
            <Button
              type="submit"
              disabled={!input.trim() || loading}
              loading={loading}
              leftIcon={<Send className="h-3.5 w-3.5" />}
            >
              Send
            </Button>
          </form>
        </CardFooter>
      </Card>
    </div>
  );
}
