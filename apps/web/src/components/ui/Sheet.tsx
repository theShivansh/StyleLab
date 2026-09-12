"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/cn";

/**
 * Dialog on desktop, bottom sheet on mobile — one component, because the composer needs the
 * same content in both places (UX-UI-SPEC sections 3 and 6).
 *
 * Built on the native <dialog> element deliberately: focus trapping, Esc-to-close, inert
 * background and the top layer come from the platform. A hand-rolled div-based modal gets
 * the focus trap wrong roughly every time, and this is a keyboard-gated product.
 */
export function Sheet({
  open,
  onClose,
  title,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    // Fires for Esc and for form-method=dialog, so the parent's state stays in sync
    // however the dialog was dismissed.
    const onCancelOrClose = () => onClose();
    dialog.addEventListener("close", onCancelOrClose);
    return () => dialog.removeEventListener("close", onCancelOrClose);
  }, [onClose]);

  return (
    <dialog
      ref={ref}
      aria-label={title}
      onClick={(event) => {
        // Backdrop click: the dialog element itself is the backdrop area.
        if (event.target === ref.current) onClose();
      }}
      className={cn(
        "bg-surface text-ink m-0 w-full max-w-none p-0 backdrop:bg-black/25",
        // Mobile: bottom sheet.
        "mt-auto rounded-t-[var(--radius-card-lg)] rounded-b-none",
        // Desktop: centred dialog.
        "md:m-auto md:max-w-lg md:rounded-[var(--radius-card-lg)]",
        "shadow-[var(--shadow-floating)]",
        "open:animate-rise",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-4 p-6 pb-0">
        <h2 className="text-title">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className={cn(
            "text-ink-muted hover:text-ink hover:bg-surface-muted -mt-1 -mr-1 grid shrink-0",
            "size-[var(--size-touch)] place-items-center rounded-[var(--radius-pill)]",
            "transition-colors duration-[var(--duration-functional)]",
          )}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <path
              d="M3 3l10 10M13 3L3 13"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>
      <div className="p-6">{children}</div>
    </dialog>
  );
}
