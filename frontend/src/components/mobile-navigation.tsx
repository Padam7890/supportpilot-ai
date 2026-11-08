"use client";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { AppSidebar } from "@/components/app-sidebar";
import type { User } from "@/features/auth/types/user.types";
import { Menu } from "lucide-react";

type MobileNavigationProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User;
  unreadCount: number;
  hasMoreUnread: boolean;
  onOpenSearch: () => void;
  onSwitchWorkspace: () => void;
};

export function MobileNavigation({ open, onOpenChange, user, unreadCount, hasMoreUnread, onOpenSearch, onSwitchWorkspace }: MobileNavigationProps) {
  return <>
    <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => onOpenChange(true)} aria-label="Open navigation"><Menu/></Button>
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent aria-label="Mobile workspace navigation">
        <AppSidebar
          user={user}
          collapsed={false}
          mobile
          unreadCount={unreadCount}
          hasMoreUnread={hasMoreUnread}
          onToggleCollapse={() => undefined}
          onOpenSearch={() => { onOpenChange(false); onOpenSearch(); }}
          onSwitchWorkspace={onSwitchWorkspace}
          onNavigate={() => onOpenChange(false)}
        />
      </SheetContent>
    </Sheet>
  </>;
}
