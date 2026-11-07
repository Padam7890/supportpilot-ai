"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { useEffect, useState, type ReactNode } from "react";
import { ensureTypographyScaleFromStorage } from "@/lib/typography-scale";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Providers({ children }: { children: ReactNode }) {
  useEffect(() => {
    ensureTypographyScaleFromStorage();
  }, []);
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false },
          mutations: { retry: 0 },
        },
      }),
  );
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider>
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </TooltipProvider>
    </MotionConfig>
  );
}
