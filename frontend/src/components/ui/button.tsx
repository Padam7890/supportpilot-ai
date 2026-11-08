import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group/button typo-button inline-flex shrink-0 items-center justify-center gap-2 rounded-md border border-transparent font-medium whitespace-nowrap transition-colors outline-none select-none focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
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
        unstyled:
          "min-h-0 border-0 bg-transparent p-0 text-inherit shadow-none hover:bg-transparent",
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-7 px-2.5 text-xs",
        lg: "h-10 px-4",
        icon: "size-9 p-0",
        "icon-sm": "size-7 p-0",
        unstyled: "",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants> & {
  loading?: boolean;
  loadingLabel?: string;
  leadingIcon?: ReactNode;
};

function Button({ className, variant = "default", size, type = "button", loading = false, loadingLabel, leadingIcon, children, disabled, ...props }: ButtonProps) {
  const resolvedSize = size ?? (variant === "unstyled" ? "unstyled" : "default");
  return (
    <button
      type={type}
      data-slot="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size: resolvedSize, className }))}
      {...props}
    >
      {loading ? <LoaderCircle aria-hidden="true" className="animate-spin"/> : leadingIcon}
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  );
}

export { Button, buttonVariants };
