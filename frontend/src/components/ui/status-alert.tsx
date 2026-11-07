import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

const toneClass: Record<"error" | "warning" | "success" | "info", string> = {
  error: "border-red-200 bg-red-50 text-red-900 [&_[data-slot=alert-description]]:text-red-800",
  warning: "border-amber-200 bg-amber-50 text-amber-950 [&_[data-slot=alert-description]]:text-amber-900",
  success: "border-emerald-200 bg-emerald-50 text-emerald-950 [&_[data-slot=alert-description]]:text-emerald-900",
  info: "border-blue-200 bg-blue-50 text-blue-950 [&_[data-slot=alert-description]]:text-blue-900",
};

export function StatusAlert({
  tone = "error",
  title,
  children,
  onRetry,
  retryLabel = "Try again",
  className,
}: {
  tone?: keyof typeof toneClass;
  title?: string;
  children: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}) {
  return (
    <Alert className={cn(toneClass[tone], className)} variant={tone === "error" ? "destructive" : "default"}>
      {title ? <AlertTitle className="text-sm font-semibold">{title}</AlertTitle> : null}
      <AlertDescription className="text-sm">
        {children}
        {onRetry ? (
          <Button type="button" variant="link" size="sm" className="mt-2 h-auto p-0" onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}
