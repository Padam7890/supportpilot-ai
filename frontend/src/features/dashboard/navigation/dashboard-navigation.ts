import {
  Activity,
  Workflow,
  BarChart3,
  BookOpen,
  Bot,
  Building2,
  Inbox,
  MessageCircle,
  PackageSearch,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";

export type DashboardNavigationLink = {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
};

export type DashboardNavigationGroup = {
  label: string;
  links: DashboardNavigationLink[];
};

const groups: DashboardNavigationGroup[] = [
  {
    label: "Workspace",
    links: [
      { href: "/dashboard", label: "Overview", icon: BarChart3, exact: true },
      { href: "/dashboard/inbox", label: "Inbox", icon: Inbox },
      { href: "/dashboard/tickets", label: "Tickets", icon: Inbox },
      { href: "/dashboard/customers", label: "Customers", icon: Users },
      { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
    ],
  },
  {
    label: "AI Studio",
    links: [
      { href: "/dashboard/ai/agents", label: "AI Bots", icon: Bot },
      { href: "/dashboard/knowledge", label: "Knowledge Library", icon: BookOpen },
      { href: "/dashboard/automations", label: "Automations", icon: Workflow },
      { href: "/dashboard/ai", label: "AI Playground", icon: Sparkles },
    ],
  },
  {
    label: "Connections",
    links: [
      { href: "/dashboard/widget", label: "Widget", icon: MessageCircle },
      { href: "/dashboard/orders", label: "Shopify orders", icon: PackageSearch },
    ],
  },
  {
    label: "Administration",
    links: [
      { href: "/dashboard/operations", label: "Operations", icon: Activity },
      { href: "/dashboard/settings", label: "Settings", icon: Building2 },
    ],
  },
];

export function getDashboardNavigation(role: string): DashboardNavigationGroup[] {
  const isWorkspaceManager = role === "owner" || role === "admin";
  return groups.map((group) => ({
    ...group,
    links: group.links.map((link) =>
      link.href === "/dashboard/settings"
        ? { ...link, label: isWorkspaceManager ? "Settings & team" : "Settings" }
        : link,
    ),
  }));
}

export function isDashboardNavigationLinkActive(pathname: string, link: DashboardNavigationLink): boolean {
  if (link.exact) return pathname === link.href;
  return pathname === link.href || pathname.startsWith(`${link.href}/`);
}
