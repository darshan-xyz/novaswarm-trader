"use client";

import React, { useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl" | "full";
  className?: string;
  closeOnClickOutside?: boolean;
  closeOnEsc?: boolean;
  showCloseButton?: boolean;
}

export function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  className,
  closeOnClickOutside = true,
  closeOnEsc = true,
  showCloseButton = true,
}: ModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (closeOnEsc && e.key === "Escape") {
        onClose();
      }
    },
    [closeOnEsc, onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    } else {
      document.body.style.overflow = "unset";
    }

    return () => {
      document.body.style.overflow = "unset";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const sizeClasses = {
    sm: "max-w-md",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
    full: "max-w-[95vw] max-h-[95vh]",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/75 backdrop-blur-sm transition-opacity"
        aria-hidden="true"
        onClick={() => {
          if (closeOnClickOutside) onClose();
        }}
      />

      {/* Modal Dialog Content */}
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative w-full rounded-xl border border-gray-800 bg-gray-900 shadow-2xl transition-all duration-200 text-gray-100 z-10 flex flex-col max-h-[90vh] overflow-hidden",
          sizeClasses[size],
          className
        )}
      >
        {/* Header */}
        {(title || showCloseButton) && (
          <div className="flex items-start justify-between border-b border-gray-800/80 px-6 py-4 shrink-0">
            <div className="space-y-1 pr-6">
              {title && (
                <h3 className="text-base font-semibold leading-6 text-gray-100">
                  {title}
                </h3>
              )}
              {description && (
                <p className="text-xs text-gray-400">{description}</p>
              )}
            </div>
            {showCloseButton && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close modal"
                className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div className="overflow-y-auto px-6 py-5 flex-1 text-sm text-gray-300">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="flex items-center justify-end gap-3 border-t border-gray-800/80 bg-gray-900/60 px-6 py-3.5 shrink-0">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// Dialog alias and composable parts
export const Dialog = Modal;

export interface DialogProps extends ModalProps {}

export default Modal;
