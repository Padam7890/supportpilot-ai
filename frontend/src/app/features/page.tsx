import { BookOpen, Inbox, MessageSquareText, PackageSearch, ShieldCheck, Sparkles, Users } from "lucide-react";
import { PublicCTA, PublicSiteLayout } from "@/components/public-site-layout";

const features = [
  { name: "Unified inbox", detail: "Filter tickets by ownership, status, priority, and search. Select a conversation explicitly when a ticket contains separate threads.", icon: Inbox },
  { name: "Customer context", detail: "Review linked tickets and recent customer messages while you work through a conversation.", icon: Users },
  { name: "Team collaboration", detail: "Claim unassigned tickets, track ticket activity, and add private internal notes that are not sent to customers.", icon: MessageSquareText },
  { name: "Knowledge search", detail: "Upload support documents, search their indexed content, and inspect source citations.", icon: BookOpen },
  { name: "AI reply drafts", detail: "Generate a grounded reply draft from conversation context and available knowledge. A teammate reviews and sends it.", icon: Sparkles },
  { name: "Shopify order lookup", detail: "Connect a store with read-only access. Order details require an exact order-number and customer-email match.", icon: PackageSearch },
  { name: "Workspace security", detail: "Tenant access is role-controlled. New workspaces wait for platform-owner review before the first owner can sign in.", icon: ShieldCheck },
];

export default function FeaturesPage() {
  return <PublicSiteLayout><main><section className="border-b border-slate-200 bg-gradient-to-b from-blue-50 to-white"><div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 sm:py-20"><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Product features</p><h1 className="mt-3 max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">A complete view of the support conversation</h1><p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">Keep people, tickets, knowledge, and verified order details connected while your team remains responsible for customer communication.</p></div></section><section className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-18"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{features.map(({ name, detail, icon: Icon }) => <article key={name} className="rounded-2xl border border-slate-200 bg-white p-6"><span className="grid size-11 place-items-center rounded-xl bg-blue-50 text-blue-700"><Icon size={20}/></span><h2 className="mt-5 font-semibold">{name}</h2><p className="mt-2 text-sm leading-6 text-slate-600">{detail}</p></article>)}</div></section><PublicCTA title="See SupportPilot in your own workspace"/></main></PublicSiteLayout>;
}
