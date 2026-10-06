"use client";

import React, { useState } from "react";
import Sidebar from "./sidebar";
import TopBar from "./top-bar";

export interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-gray-950 text-gray-100 antialiased selection:bg-blue-600/30 selection:text-blue-200">
      {/* Persistent / responsive sidebar */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main column */}
      <div className="flex flex-1 flex-col min-w-0">
        <TopBar onOpenSidebar={() => setSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          {children}
        </main>
      </div>
    </div>
  );
}

export default AppShell;
