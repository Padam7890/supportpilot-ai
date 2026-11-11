import {
  Activity,
  BriefcaseBusiness,
  Workflow,
  BarChart3,
  BookOpen,
  Bot,
  Building2,
  Inbox,
  MessageCircle,
  MessageSquareText,
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
  parentHref?: string;
};

export type DashboardNavigationGroup = {
  label: string;
  links: DashboardNavigationLink[];
};

const groups: DashboardNavigationGroup[] = [
  {
    label: "Main",
    links: [
      { href: "/dashboard", label: "Overview", icon: BarChart3, exact: true },
      { href: "/dashboard/inbox", label: "Inbox", icon: Inbox },
      { href: "/dashboard/customers", label: "Customers", icon: Users },
    ],
  },
  {
    label: "AI & automation",
    links: [
      { href: "/dashboard/ai/agents", label: "AI Agents", icon: Bot },
      { href: "/dashboard/knowledge", label: "Knowledge", icon: BookOpen },
      { href: "/dashboard/knowledge/customer-questions", label: "Customer questions", icon: MessageSquareText, parentHref: "/dashboard/knowledge" },
      { href: "/dashboard/automations", label: "Automations", icon: Workflow },
      { href: "/dashboard/ai", label: "AI Playground", icon: Sparkles },
    ],
  },
  {
    label: "Insights",
    links: [
      { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/dashboard/operations", label: "Activity logs", icon: Activity },
    ],
  },
  {
    label: "Workspace",
    links: [
      { href: "/dashboard/tickets", label: "Tickets", icon: Inbox },
      { href: "/dashboard/widget", label: "Channels", icon: MessageCircle },
      { href: "/dashboard/settings#shopify", label: "Integrations", icon: BriefcaseBusiness },
      { href: "/dashboard/orders", label: "Shopify orders", icon: PackageSearch },
      { href: "/dashboard/settings", label: "Settings", icon: Building2 },
    ],
  },
];

export function getDashboardNavigation(role: string): DashboardNavigationGroup[] {
  const isWorkspaceManager = role === "owner" || role === "admin";
  return groups.map((group) => ({
    ...group,
    links: group.links
      .filter((link) => (link.href !== "/dashboard/operations" || role !== "viewer")
        && (link.href !== "/dashboard/knowledge/customer-questions" || isWorkspaceManager))
      .map((link) => link.href === "/dashboard/settings" && !link.href.includes("#")
        ? { ...link, label: isWorkspaceManager ? "Settings & team" : "Settings" }
        : link),
  }));
}

export function isDashboardNavigationLinkActive(pathname: string, link: DashboardNavigationLink): boolean {
  const route = link.href.split("#", 1)[0];
  if (link.exact) return pathname === route;
  return pathname === route || pathname.startsWith(`${route}/`);
}
