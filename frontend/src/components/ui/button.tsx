import type { ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group/button typo-button inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-transparent font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--text-accent)] text-[var(--text-on-accent)] shadow-sm hover:bg-[#1d4ed8]",
        primary:
          "bg-[var(--text-accent)] text-[var(--text-on-accent)] shadow-sm hover:bg-[#1d4ed8]",
        outline:
          "border-border bg-background text-foreground hover:bg-muted",
        secondary:
          "border border-border bg-secondary text-secondary-foreground hover:bg-muted",
        ghost: "text-foreground hover:bg-muted",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        danger:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        link: "text-[var(--text-accent)] underline-offset-4 hover:underline",
      },
      size: {
        default: "min-h-10 px-4",
        sm: "min-h-9 px-3 text-[0.8125rem]",
        lg: "min-h-11 px-5",
        icon: "size-9",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

function Button({ className, variant = "default", size = "default", type = "button", ...props }: ButtonProps) {
  return (
    <button
      type={type}
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
