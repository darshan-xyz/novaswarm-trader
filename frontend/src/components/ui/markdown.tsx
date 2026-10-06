"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";

export interface MarkdownProps {
  content: string;
  className?: string;
}

export function Markdown({ content, className }: MarkdownProps) {
  if (!content) {
    return null;
  }
  const safeContent = typeof content === "string" ? content : String(content);

  return (
    <div
      className={cn(
        "prose prose-invert max-w-none text-xs sm:text-sm leading-relaxed text-gray-300 space-y-3",
        className
      )}
    >
      <ReactMarkdown
        components={{
          h1: ({ children }) => (
            <h1 className="text-lg font-bold text-gray-100 mt-4 mb-2 pb-1 border-b border-gray-800">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold text-gray-100 mt-3 mb-1.5 pb-0.5 border-b border-gray-850">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold text-gray-200 mt-2.5 mb-1">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="mb-2 leading-relaxed text-gray-300">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 mb-2 space-y-1 text-gray-300">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 mb-2 space-y-1 text-gray-300">
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-blue-500 pl-3 italic text-gray-400 my-2 bg-blue-950/20 py-1 rounded-r">
              {children}
            </blockquote>
          ),
          code: ({ className, children, ...props }) => {
            const isBlock = Boolean(className) || String(children).includes("\n");
            if (isBlock) {
              return (
                <code
                  className={cn(
                    "block bg-gray-950 text-gray-200 p-3 rounded-lg border border-gray-800 font-mono text-xs overflow-x-auto my-2",
                    className
                  )}
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className="bg-gray-800/90 text-blue-300 px-1.5 py-0.5 rounded text-[11px] font-mono border border-gray-750"
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className="my-2">{children}</pre>,
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 rounded-lg border border-gray-800">
              <table className="w-full text-left text-xs border-collapse">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-gray-900 border-b border-gray-800 text-gray-400 font-medium">
              {children}
            </thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-gray-800/60 bg-gray-950/40">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-gray-800/30 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 font-semibold uppercase tracking-wider text-[11px] text-gray-400">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-gray-300">{children}</td>
          ),
          hr: () => <hr className="border-gray-800 my-3" />,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 underline underline-offset-2"
            >
              {children}
            </a>
          ),
        }}
      >
        {safeContent}
      </ReactMarkdown>
    </div>
  );
}

export default Markdown;
