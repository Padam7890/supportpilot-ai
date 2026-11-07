"use client";

import { useSyncExternalStore } from "react";
import {
  readTypographyScale,
  setTypographyScale,
  TYPOGRAPHY_SCALE_CHANGE_EVENT,
  type TypographyScale,
} from "@/lib/typography-scale";
import { cn } from "@/lib/utils";

const OPTIONS: { id: TypographyScale; label: string; description: string; preview: { menu: string; body: string; title: string } }[] = [
  {
    id: "compact",
    label: "Compact",
    description: "Dense tables and power-user workflows.",
    preview: { menu: "13px", body: "13px", title: "22px" },
  },
  {
    id: "balanced",
    label: "Balanced",
    description: "Default — sidebar at 13px, body at 14px.",
    preview: { menu: "13px", body: "14px", title: "24px" },
  },
  {
    id: "comfortable",
    label: "Comfortable",
    description: "Larger type and spacing for readability.",
    preview: { menu: "14px", body: "15px", title: "26px" },
  },
];

function subscribe(callback: () => void) {
  window.addEventListener(TYPOGRAPHY_SCALE_CHANGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(TYPOGRAPHY_SCALE_CHANGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function getSnapshot(): TypographyScale {
  return readTypographyScale();
}

function getServerSnapshot(): TypographyScale {
  return "balanced";
}

export function TypographyScalePicker() {
  const scale = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {OPTIONS.map((option) => {
          const selected = scale === option.id;
          return (
            <button
              key={option.id}
              type="button"
              aria-pressed={selected}
              onClick={() => setTypographyScale(option.id)}
              className={cn(
                "rounded-xl border p-4 text-left transition",
                selected
                  ? "border-blue-600 bg-blue-50/80 ring-2 ring-blue-600/20"
                  : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
              )}
            >
              <p className="card-title text-[var(--text-primary)]">{option.label}</p>
              <p className="helper-text mt-1 text-[var(--text-muted)]">{option.description}</p>
              <dl className="meta-text mt-3 space-y-0.5 text-[var(--text-secondary)]">
                <div className="flex justify-between gap-2">
                  <dt>Menu</dt>
                  <dd className="font-medium tabular-nums">{option.preview.menu}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Body</dt>
                  <dd className="font-medium tabular-nums">{option.preview.body}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt>Title</dt>
                  <dd className="font-medium tabular-nums">{option.preview.title}</dd>
                </div>
              </dl>
            </button>
          );
        })}
      </div>
      <p className="helper-text text-[var(--text-muted)]">
        Uses Inter across the app and JetBrains Mono for code, IDs, and logs. Saved in this browser only.
      </p>
    </div>
  );
}
