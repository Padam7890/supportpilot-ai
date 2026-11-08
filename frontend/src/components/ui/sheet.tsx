"use client";

import type { ComponentProps } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const Sheet = Dialog;
const SheetTrigger = DialogTrigger;
const SheetTitle = DialogTitle;
const SheetDescription = DialogDescription;
const SheetHeader = DialogHeader;
const SheetFooter = DialogFooter;

function SheetContent({ className, children, ...props }: ComponentProps<typeof DialogContent>) {
  return (
    <DialogContent
      showCloseButton={false}
      className={cn(
        "fixed inset-y-0 left-0 top-0 h-dvh w-[min(248px,calc(100vw-2rem))] max-w-none translate-x-0 translate-y-0 overflow-hidden rounded-none border-r p-0 sm:max-w-none",
        className,
      )}
      {...props}
    >
      {children}
    </DialogContent>
  );
}

export { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle, SheetTrigger };
