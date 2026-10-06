import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind CSS classes cleanly without conflict.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format a number as Indian Rupee (INR) currency.
 * e.g. 125000 -> ₹1,25,000.00 or ₹1.25L in compact mode.
 */
export function formatINR(
  value: number | null | undefined,
  compact: boolean = false
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "₹0.00";
  }

  if (compact && Math.abs(value) >= 10000000) {
    return `₹${(value / 10000000).toFixed(2)} Cr`;
  }
  if (compact && Math.abs(value) >= 100000) {
    return `₹${(value / 100000).toFixed(2)} L`;
  }
  if (compact && Math.abs(value) >= 1000) {
    return `₹${(value / 1000).toFixed(1)}k`;
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Format percentage with optional +/- sign.
 * e.g. 2.45 -> "+2.45%"
 */
export function formatPct(
  value: number | null | undefined,
  includeSign: boolean = true,
  decimals: number = 2
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "0.00%";
  }

  const sign = includeSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}%`;
}

/**
 * Format a number with Indian thousand/lakh separators.
 */
export function formatNumber(
  value: number | null | undefined,
  decimals: number = 0
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return "0";
  }

  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Format timestamp or ISO string in Indian Standard Time (IST).
 */
export function formatDateIST(
  dateValue: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string {
  if (!dateValue) return "-";
  const date = new Date(dateValue);
  if (isNaN(date.getTime())) return "-";

  const defaultOptions: Intl.DateTimeFormatOptions = {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...options,
  };

  return new Intl.DateTimeFormat("en-IN", defaultOptions).format(date);
}

/**
 * Truncate long text cleanly.
 */
export function truncate(text: string, maxLen: number = 50): string {
  if (!text) return "";
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...";
}
