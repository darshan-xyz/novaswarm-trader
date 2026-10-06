"use client";

import React, { createContext, useContext, useState } from "react";
import { cn } from "@/lib/utils";

interface TabsContextValue {
  activeTab: string;
  setActiveTab: (val: string) => void;
}

const TabsContext = createContext<TabsContextValue | undefined>(undefined);

export interface TabsProps extends React.HTMLAttributes<HTMLDivElement> {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  children: React.ReactNode;
}

export function Tabs({
  value,
  defaultValue,
  onValueChange,
  className,
  children,
  ...props
}: TabsProps) {
  const [uncontrolledValue, setUncontrolledValue] = useState<string>(
    defaultValue || ""
  );

  const isControlled = value !== undefined;
  const activeTab = isControlled ? value : uncontrolledValue;

  const handleTabChange = (newVal: string) => {
    if (!isControlled) {
      setUncontrolledValue(newVal);
    }
    onValueChange?.(newVal);
  };

  return (
    <TabsContext.Provider
      value={{ activeTab, setActiveTab: handleTabChange }}
    >
      <div className={cn("w-full space-y-4", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

export interface TabsListProps
  extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
}

export function TabsList({ className, children, ...props }: TabsListProps) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex h-10 items-center justify-start rounded-lg bg-gray-900 p-1 text-gray-400 border border-gray-800 gap-1",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export interface TabsTriggerProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  value: string;
  children: React.ReactNode;
}

export function TabsTrigger({
  value,
  className,
  children,
  ...props
}: TabsTriggerProps) {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("TabsTrigger must be used within a Tabs component");
  }

  const isActive = context.activeTab === value;

  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      onClick={() => context.setActiveTab(value)}
      className={cn(
        "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium ring-offset-gray-950 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 select-none",
        isActive
          ? "bg-gray-800 text-blue-400 font-semibold shadow-sm shadow-black/40 border border-gray-750"
          : "text-gray-400 hover:text-gray-200 hover:bg-gray-850/50",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export interface TabsContentProps
  extends React.HTMLAttributes<HTMLDivElement> {
  value: string;
  children: React.ReactNode;
}

export function TabsContent({
  value,
  className,
  children,
  ...props
}: TabsContentProps) {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("TabsContent must be used within a Tabs component");
  }

  if (context.activeTab !== value) {
    return null;
  }

  return (
    <div
      role="tabpanel"
      tabIndex={0}
      className={cn(
        "mt-2 ring-offset-gray-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export default Tabs;
