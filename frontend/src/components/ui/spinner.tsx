import React from "react";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

export interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  color?:
    | "default"
    | "current"
    | "white"
    | "emerald"
    | "amber"
    | "rose"
    | "gray";
  center?: boolean;
  label?: string;
}

export function Spinner({
  size = "md",
  color = "default",
  center = false,
  label,
  className,
  ...props
}: SpinnerProps) {
  const sizeMap = {
    xs: "h-3 w-3",
    sm: "h-4 w-4",
    md: "h-6 w-6",
    lg: "h-8 w-8",
    xl: "h-12 w-12",
  };

  const colorMap = {
    default: "text-blue-500",
    current: "text-current",
    white: "text-white",
    emerald: "text-emerald-500",
    amber: "text-amber-500",
    rose: "text-rose-500",
    gray: "text-gray-400",
  };

  const spinnerContent = (
    <div
      className={cn(
        "inline-flex items-center gap-2 text-xs text-gray-400 select-none",
        className
      )}
      {...props}
    >
      <Loader2
        className={cn("animate-spin shrink-0", sizeMap[size], colorMap[color])}
      />
      {label && <span>{label}</span>}
    </div>
  );

  if (center) {
    return (
      <div className="flex h-48 w-full items-center justify-center">
        {spinnerContent}
      </div>
    );
  }

  return spinnerContent;
}

export default Spinner;
