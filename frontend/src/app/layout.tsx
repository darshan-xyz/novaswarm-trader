import type { Metadata } from "next";
import "./globals.css";
import AppShell from "@/components/layout/app-shell";

export const metadata: Metadata = {
  title: "SkopaqTrader - Autonomous AI Trading Platform",
  description:
    "Autonomous AI multi-agent algorithmic trading platform for Indian equities (NSE)",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-gray-950 text-gray-100 min-h-screen">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
