import React, { forwardRef } from "react";
import { cn } from "@/lib/utils";
import { Loader2 } from "lucide-react";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:
    | "default"
    | "secondary"
    | "destructive"
    | "outline"
    | "ghost"
    | "success"
    | "warning";
  size?: "sm" | "md" | "lg" | "icon";
  loading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "default",
      size = "md",
      loading = false,
      disabled,
      children,
      leftIcon,
      rightIcon,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "inline-flex items-center justify-center font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950 disabled:opacity-50 disabled:pointer-events-none select-none rounded-lg";

    const variantStyles = {
      default:
        "bg-blue-600 text-white hover:bg-blue-500 active:bg-blue-700 shadow-sm shadow-blue-900/30",
      secondary:
        "bg-gray-800 text-gray-100 hover:bg-gray-700 active:bg-gray-750 border border-gray-700",
      destructive:
        "bg-rose-600 text-white hover:bg-rose-500 active:bg-rose-700 shadow-sm shadow-rose-900/30",
      outline:
        "border border-gray-700 bg-transparent text-gray-200 hover:bg-gray-800/80 active:bg-gray-800",
      ghost:
        "bg-transparent text-gray-300 hover:bg-gray-800 hover:text-white",
      success:
        "bg-emerald-600 text-white hover:bg-emerald-500 active:bg-emerald-700 shadow-sm shadow-emerald-900/30",
      warning:
        "bg-amber-600 text-white hover:bg-amber-500 active:bg-amber-700 shadow-sm shadow-amber-900/30",
    };

    const sizeStyles = {
      sm: "h-8 px-3 text-xs gap-1.5",
      md: "h-9 px-4 text-sm gap-2",
      lg: "h-11 px-6 text-base gap-2.5",
      icon: "h-9 w-9 p-0",
    };

    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin text-current" />
        ) : (
          leftIcon
        )}
        {children}
        {!loading && rightIcon}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;
