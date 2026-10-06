"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Briefcase,
  ScanSearch,
  Cpu,
  History,
  MessageSquareCode,
  TrendingUp,
  Settings,
  ShieldAlert,
  Radio,
  X,
} from "lucide-react";

export interface NavItem {
  name: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    name: "System Overview",
    href: "/",
    icon: LayoutDashboard,
  },
  {
    name: "Portfolio & Positions",
    href: "/portfolio",
    icon: Briefcase,
  },
  {
    name: "Market Scanner",
    href: "/scanner",
    icon: ScanSearch,
  },
  {
    name: "Multi-Agent Analysis",
    href: "/analysis",
    icon: Cpu,
  },
  {
    name: "Trades History",
    href: "/trades",
    icon: History,
  },
  {
    name: "AI Trading Chat",
    href: "/chat",
    icon: MessageSquareCode,
  },
  {
    name: "Performance Analytics",
    href: "/analytics",
    icon: TrendingUp,
  },
  {
    name: "Settings & Health",
    href: "/settings",
    icon: Settings,
  },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Panel */}
      <aside
        className={cn(
          "fixed top-0 bottom-0 left-0 z-50 flex w-64 flex-col border-r border-gray-800 bg-gray-900/95 backdrop-blur-md transition-transform duration-300 ease-in-out lg:static lg:translate-x-0",
          isOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-gray-800/80 px-5">
          <Link
            href="/"
            onClick={() => onClose()}
            className="flex items-center gap-2.5 group"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600/20 border border-blue-500/40 text-blue-400 group-hover:bg-blue-600/30 transition-colors">
              <Radio className="h-5 w-5 animate-pulse text-blue-400" />
            </div>
            <div className="flex flex-col">
              <span className="text-base font-bold tracking-tight text-white">
                NovaSwarm<span className="text-blue-400">Trader</span>
              </span>
              <span className="text-[10px] text-gray-400 font-medium tracking-wide">
                AI Autonomous Swarm
              </span>
            </div>
          </Link>

          {/* Close button on mobile */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sidebar"
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-100 lg:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
            Navigation
          </div>
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname?.startsWith(item.href);

            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => onClose()}
                className={cn(
                  "group flex items-center justify-between rounded-lg px-3 py-2.5 text-xs font-medium transition-all select-none",
                  isActive
                    ? "bg-blue-600/15 text-blue-400 font-semibold border border-blue-500/30 shadow-sm shadow-blue-950"
                    : "text-gray-400 hover:bg-gray-800/70 hover:text-gray-200"
                )}
              >
                <div className="flex items-center gap-3">
                  <Icon
                    className={cn(
                      "h-4 w-4 shrink-0 transition-colors",
                      isActive
                        ? "text-blue-400"
                        : "text-gray-400 group-hover:text-gray-200"
                    )}
                  />
                  <span>{item.name}</span>
                </div>
                {item.badge && (
                  <span className="rounded-full bg-blue-900/50 px-2 py-0.5 text-[10px] font-semibold text-blue-300 border border-blue-800/50">
                    {item.badge}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* System Mode & Health Status Footer */}
        <div className="border-t border-gray-800/80 p-3.5 space-y-2.5 bg-gray-950/40">
          <div className="flex items-center justify-between rounded-lg border border-gray-800 bg-gray-900/80 px-3 py-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
              </span>
              <span className="font-medium text-gray-300">Trading Mode</span>
            </div>
            <span className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider bg-amber-950/70 text-amber-400 border border-amber-800/50">
              PAPER
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-gray-500 px-1">
            <span>Broker: INDstocks / Paper</span>
            <span className="font-mono text-[10px]">v0.1.0</span>
          </div>
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
