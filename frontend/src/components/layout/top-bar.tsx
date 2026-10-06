"use client";

import React, { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Menu, Clock, ShieldCheck } from "lucide-react";
import { formatDateIST } from "@/lib/utils";

interface TopBarProps {
  onOpenSidebar: () => void;
}

const ROUTE_TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": {
    title: "System Overview",
    subtitle: "Real-time infrastructure health, connectivity & portfolio summary",
  },
  "/portfolio": {
    title: "Portfolio & Positions",
    subtitle: "Live capital, intraday open positions & order book",
  },
  "/scanner": {
    title: "Market Scanner",
    subtitle: "Real-time momentum radar, catalyst screeners & candidate confluence",
  },
  "/analysis": {
    title: "Multi-Agent Analysis",
    subtitle: "Live streaming graph execution across Analyst, Debate & Risk swarms",
  },
  "/trades": {
    title: "Trades History",
    subtitle: "Auditable paper & live executions with model predictions and reflections",
  },
  "/chat": {
    title: "AI Trading Chat",
    subtitle: "Conversational trading intelligence with live tool invocations",
  },
  "/analytics": {
    title: "Performance Analytics",
    subtitle: "Equity curves, drawdown analysis & LLM prediction accuracy",
  },
  "/settings": {
    title: "Settings & System Health",
    subtitle: "Strategy DNA governance, model routing & safety simulation",
  },
};

export function TopBar({ onOpenSidebar }: TopBarProps) {
  const pathname = usePathname();
  const [timeStr, setTimeStr] = useState<string>("");
  const [isMarketOpen, setIsMarketOpen] = useState<boolean>(false);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(
        formatDateIST(now, {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          day: "2-digit",
          month: "short",
        })
      );

      // NSE market hours: 09:15 to 15:30 IST, Monday-Friday
      const istHours = (now.getUTCHours() + 5 + (now.getUTCMinutes() + 30 >= 60 ? 1 : 0)) % 24;
      const istMinutes = (now.getUTCMinutes() + 30) % 60;
      const dayOfWeek = now.getUTCDay(); // 0 is Sunday, 6 is Saturday
      const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
      const totalMinutes = istHours * 60 + istMinutes;
      const marketOpen = 9 * 60 + 15;
      const marketClose = 15 * 60 + 30;
      setIsMarketOpen(isWeekday && totalMinutes >= marketOpen && totalMinutes <= marketClose);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const routeInfo = ROUTE_TITLES[pathname || "/"] || {
    title: "SkopaqTrader",
    subtitle: "Autonomous AI Algorithmic Trading",
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-gray-800 bg-gray-950/80 px-4 sm:px-6 backdrop-blur-md">
      {/* Left: Mobile Menu + Title */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onOpenSidebar}
          aria-label="Open sidebar"
          className="rounded-lg p-2 text-gray-400 hover:bg-gray-800 hover:text-gray-100 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div>
          <h1 className="text-sm sm:text-base font-semibold text-gray-100 tracking-tight">
            {routeInfo.title}
          </h1>
          <p className="hidden md:block text-[11px] text-gray-400">
            {routeInfo.subtitle}
          </p>
        </div>
      </div>

      {/* Right: Market Status, Clock & Safety Badge */}
      <div className="flex items-center gap-2.5 sm:gap-3">
        {/* Market Status Pill */}
        <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-gray-800 bg-gray-900/90 px-2.5 py-1 text-[11px]">
          <span
            className={`h-2 w-2 rounded-full ${
              isMarketOpen ? "bg-emerald-400 animate-pulse" : "bg-gray-500"
            }`}
          />
          <span className="font-medium text-gray-300">
            NSE: {isMarketOpen ? "OPEN" : "CLOSED"}
          </span>
        </div>

        {/* Safety Engine Badge */}
        <div className="hidden md:flex items-center gap-1.5 rounded-full border border-emerald-800/60 bg-emerald-950/30 px-2.5 py-1 text-[11px] text-emerald-400">
          <ShieldCheck className="h-3.5 w-3.5" />
          <span className="font-medium">Risk Shield Active</span>
        </div>

        {/* IST Clock */}
        <div className="flex items-center gap-1.5 rounded-lg border border-gray-800 bg-gray-900/90 px-2.5 py-1 text-xs text-gray-300 font-mono">
          <Clock className="h-3.5 w-3.5 text-gray-400 shrink-0" />
          <span className="text-[11px] sm:text-xs">{timeStr || "Loading..."}</span>
        </div>
      </div>
    </header>
  );
}

export default TopBar;
