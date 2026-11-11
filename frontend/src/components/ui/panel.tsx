import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function Panel({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <Card
      data-slot="panel"
      className={cn("rounded-2xl shadow-sm ring-border/60", className)}
      {...(props as HTMLAttributes<HTMLDivElement>)}
    />
  );
}

export function PanelHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <CardHeader className="border-b border-border/60 pb-4">
      <CardTitle role="heading" aria-level={2} className="card-title font-semibold">{title}</CardTitle>
      {description ? <CardDescription className="helper-text">{description}</CardDescription> : null}
      {action ? <CardAction>{action}</CardAction> : null}
    </CardHeader>
  );
}

export function PanelBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <CardContent className={cn("sm:p-6", className)} {...props} />;
}
