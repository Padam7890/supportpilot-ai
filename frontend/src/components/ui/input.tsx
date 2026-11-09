import * as React from "react";
import { Input as InputPrimitive } from "@base-ui/react/input";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Textarea as TextareaPrimitive } from "@/components/ui/textarea";

const fieldClassName =
  "typo-input w-full min-w-0 rounded-md border border-input bg-background px-3 text-foreground transition-[border-color,box-shadow,background-color] outline-none placeholder:text-muted-foreground/80 focus-visible:border-primary/70 focus-visible:ring-1 focus-visible:ring-primary/20 disabled:cursor-not-allowed disabled:bg-muted/60 disabled:text-muted-foreground disabled:opacity-70 read-only:bg-muted/40 read-only:text-muted-foreground";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(fieldClassName, "h-10 py-2", className)}
      {...props}
    />
  );
}

function Select({ className, ...props }: React.ComponentProps<"select">) {
  const layoutClasses = className
    ?.split(/\s+/)
    .filter((token) => /^(w-|min-w-|max-w-|flex-)/.test(token))
    .join(" ");

  return (
    <span className={cn("relative block w-full min-w-0", layoutClasses)}>
      <select
        data-slot="select"
        className={cn(
          fieldClassName,
          "h-10 appearance-none py-2 pr-10 hover:border-ring/50 focus-visible:border-primary/60 focus-visible:ring-1 focus-visible:ring-primary/15",
          className,
        )}
        {...props}
      />
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
      />
    </span>
  );
}

const Textarea = React.forwardRef<HTMLTextAreaElement, React.ComponentProps<"textarea">>(
  ({ className, ...props }, ref) => (
    <TextareaPrimitive
      ref={ref}
      className={cn(fieldClassName, "min-h-28 py-3", className)}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export { Input, Select, Textarea };
