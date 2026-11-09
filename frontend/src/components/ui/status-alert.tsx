import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

const toneClass: Record<"error" | "warning" | "success" | "info", string> = {
  error: "border-error/30 bg-error/10 text-error-foreground [&_[data-slot=alert-description]]:text-error-foreground",
  warning: "border-warning/30 bg-warning/10 text-warning-foreground [&_[data-slot=alert-description]]:text-warning-foreground",
  success: "border-success/30 bg-success/10 text-success-foreground [&_[data-slot=alert-description]]:text-success-foreground",
  info: "border-info/30 bg-info/10 text-info-foreground [&_[data-slot=alert-description]]:text-info-foreground",
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
