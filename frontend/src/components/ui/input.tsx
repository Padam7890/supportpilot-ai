import * as React from "react";
import { Input as InputPrimitive } from "@base-ui/react/input";
import { cn } from "@/lib/utils";
import { Textarea as TextareaPrimitive } from "@/components/ui/textarea";

const fieldClassName =
  "typo-input w-full min-w-0 rounded-lg border border-input bg-background px-3 shadow-sm transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(fieldClassName, "min-h-10 py-2", className)}
      {...props}
    />
  );
}

function Select({ className, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="select"
      className={cn(fieldClassName, "min-h-10 py-2", className)}
      {...props}
    />
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
