import type { InputHTMLAttributes, Ref, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "typo-input min-h-10 w-full rounded-xl border border-slate-200 bg-white px-3.5 shadow-sm outline-none placeholder:text-[var(--text-disabled)] focus:border-blue-300 focus:ring-0 focus-visible:outline-none! disabled:bg-slate-100",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: InputHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "typo-input min-h-10 w-full rounded-xl border border-slate-200 bg-white px-3.5 shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ref, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement> & { ref?: Ref<HTMLTextAreaElement> }) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "typo-input min-h-28 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 shadow-sm outline-none placeholder:text-[var(--text-disabled)] focus:border-blue-500 focus:ring-2 focus:ring-blue-100",
        className,
      )}
      {...props}
    />
  );
}
