import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";

export function FormField({
  label,
  error,
  hint,
  className,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label className="form-label">{label}</Label>
      {children}
      {hint ? <p className="helper-text">{hint}</p> : null}
      {error ? (
        <p role="alert" className="helper-text text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
