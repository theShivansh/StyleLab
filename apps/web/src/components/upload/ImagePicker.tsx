"use client";

import { useCallback, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { config } from "@/lib/config";
import { partitionBatch } from "@/lib/validate-image";

/**
 * Multi-image picker. One gesture, many photos.
 *
 * Both paths are real inputs rather than a styled div: the file input stays in the DOM and
 * keyboard/AT users get the native picker, while drag-and-drop is an enhancement layered on
 * top. UX-UI-SPEC forbids hover-only critical actions, and a drop zone with no button is
 * exactly that.
 */
export function ImagePicker({
  onPicked,
  disabled = false,
}: {
  onPicked: (files: File[], rejected: Array<{ name: string; message: string }>) => void;
  disabled?: boolean;
}) {
  const inputId = useId();
  const hintId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [draggingOver, setDraggingOver] = useState(false);

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0) return;

      const files = Array.from(fileList);
      const { accepted, rejected, overflow } = partitionBatch(files);

      const messages = rejected.map(({ file, rejection }) => ({
        name: file.name,
        message: rejection.message,
      }));

      // Over-count is surfaced, not silently truncated. Dropping a user's file without
      // telling them is worse than refusing it out loud.
      for (const file of overflow) {
        messages.push({
          name: file.name,
          message: `Only ${config.upload.maxImagesPerBatch} photos at a time — add this one next.`,
        });
      }

      onPicked(accepted, messages);
    },
    [onPicked],
  );

  return (
    <div
      onDragOver={(event) => {
        if (disabled) return;
        event.preventDefault();
        setDraggingOver(true);
      }}
      onDragLeave={() => setDraggingOver(false)}
      onDrop={(event) => {
        if (disabled) return;
        event.preventDefault();
        setDraggingOver(false);
        handleFiles(event.dataTransfer.files);
      }}
      className={cn(
        "rounded-[var(--radius-card)] border-2 border-dashed p-8 text-center transition-colors",
        "duration-[var(--duration-functional)]",
        draggingOver ? "border-accent bg-accent-soft/40" : "border-border-strong bg-surface",
        disabled && "pointer-events-none opacity-50",
      )}
    >
      <label htmlFor={inputId} className="text-title block cursor-pointer">
        Add garments
      </label>
      <p id={hintId} className="text-ink-muted mx-auto mt-2 max-w-[44ch] text-sm">
        Up to {config.upload.maxImagesPerBatch} photos at once. One garment per frame, plain
        background, even light. JPEG, PNG, WebP or AVIF under{" "}
        {Math.round(config.upload.maxBytes / (1024 * 1024))} MB.
      </p>

      <input
        ref={inputRef}
        id={inputId}
        type="file"
        multiple
        accept={config.upload.acceptedMimeTypes.join(",")}
        aria-describedby={hintId}
        className="sr-only"
        onChange={(event) => {
          handleFiles(event.target.files);
          // Reset so picking the same file twice still fires a change event.
          event.target.value = "";
        }}
      />

      <div className="mt-5 flex flex-col items-center gap-2 sm:flex-row sm:justify-center">
        <Button size="lg" onClick={() => inputRef.current?.click()} disabled={disabled}>
          Choose photos
        </Button>
        <span className="text-ink-muted hidden text-sm sm:inline">or drop them here</span>
      </div>
    </div>
  );
}
