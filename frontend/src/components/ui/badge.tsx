import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?:
    | "default"
    | "secondary"
    | "success"
    | "danger"
    | "warning"
    | "info"
    | "outline";
  size?: "sm" | "md";
  dot?: boolean;
}

export const Badge = forwardRef<HTMLDivElement, BadgeProps>(
  (
    {
      className,
      variant = "default",
      size = "md",
      dot = false,
      children,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "inline-flex items-center font-medium rounded-full transition-colors select-none";

    const sizeStyles = {
      sm: "px-2 py-0.5 text-[10px] gap-1",
      md: "px-2.5 py-1 text-xs gap-1.5",
    };

    const variantStyles = {
      default:
        "bg-blue-900/30 text-blue-400 border border-blue-800/60",
      secondary:
        "bg-gray-800 text-gray-300 border border-gray-700",
      success:
        "bg-emerald-950/40 text-emerald-400 border border-emerald-800/60",
      danger:
        "bg-rose-950/40 text-rose-400 border border-rose-800/60",
      warning:
        "bg-amber-950/40 text-amber-400 border border-amber-800/60",
      info:
        "bg-cyan-950/40 text-cyan-400 border border-cyan-800/60",
      outline:
        "bg-transparent text-gray-300 border border-gray-700",
    };

    const dotColors = {
      default: "bg-blue-400",
      secondary: "bg-gray-400",
      success: "bg-emerald-400 animate-pulse",
      danger: "bg-rose-400",
      warning: "bg-amber-400",
      info: "bg-cyan-400",
      outline: "bg-gray-400",
    };

    return (
      <div
        ref={ref}
        className={cn(baseStyles, sizeStyles[size], variantStyles[variant], className)}
        {...props}
      >
        {dot && (
          <span
            className={cn("h-1.5 w-1.5 rounded-full shrink-0", dotColors[variant])}
          />
        )}
        {children}
      </div>
    );
  }
);

Badge.displayName = "Badge";

export default Badge;
