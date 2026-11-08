import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: string;
  eyebrow?: string;
  actions?: ReactNode;
};

export function PageHeader({ title, description, eyebrow, actions }: PageHeaderProps) {
  return <div className="flex min-h-16 flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
    <div className="min-w-0">
      {eyebrow && <p className="mb-1 text-xs font-semibold text-primary">{eyebrow}</p>}
      <h1 className="text-xl font-semibold tracking-tight text-foreground sm:text-2xl">{title}</h1>
      {description && <p className="mt-1 max-w-3xl text-sm leading-5 text-muted-foreground">{description}</p>}
    </div>
    {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
  </div>;
}
