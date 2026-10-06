import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

export interface StatCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  value: React.ReactNode;
  subtitle?: React.ReactNode;
  change?: number; // e.g. 2.45 (%)
  changeLabel?: string; // e.g. "vs yesterday"
  isPositive?: boolean;
  icon?: React.ReactNode;
  loading?: boolean;
}

export const StatCard = forwardRef<HTMLDivElement, StatCardProps>(
  (
    {
      className,
      title,
      value,
      subtitle,
      change,
      changeLabel,
      isPositive,
      icon,
      loading = false,
      ...props
    },
    ref
  ) => {
    // Infer positivity if not explicitly provided
    const positive = isPositive !== undefined ? isPositive : (change !== undefined ? change >= 0 : undefined);

    return (
      <div
        ref={ref}
        className={cn(
          "rounded-xl border border-gray-800 bg-gray-900/90 p-5 shadow-sm backdrop-blur-sm transition-all hover:border-gray-700/80",
          className
        )}
        {...props}
      >
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wider text-gray-400">
            {title}
          </span>
          {icon && (
            <div className="rounded-lg bg-gray-800/80 p-2 text-gray-300">
              {icon}
            </div>
          )}
        </div>

        <div className="mt-3">
          {loading ? (
            <div className="h-8 w-28 animate-pulse rounded bg-gray-800" />
          ) : (
            <div className="text-2xl font-bold tracking-tight text-gray-100">
              {value}
            </div>
          )}
        </div>

        {(change !== undefined || subtitle) && (
          <div className="mt-2.5 flex items-center gap-2 text-xs">
            {change !== undefined && (
              <span
                className={cn(
                  "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 font-medium",
                  positive
                    ? "bg-emerald-950/50 text-emerald-400 border border-emerald-850"
                    : "bg-rose-950/50 text-rose-400 border border-rose-850"
                )}
              >
                {positive ? (
                  <ArrowUpRight className="h-3 w-3" />
                ) : (
                  <ArrowDownRight className="h-3 w-3" />
                )}
                {change > 0 ? `+${change.toFixed(2)}%` : `${change.toFixed(2)}%`}
              </span>
            )}
            {changeLabel && <span className="text-gray-500">{changeLabel}</span>}
            {subtitle && <span className="text-gray-400 truncate">{subtitle}</span>}
          </div>
        )}
      </div>
    );
  }
);

StatCard.displayName = "StatCard";

export default StatCard;
