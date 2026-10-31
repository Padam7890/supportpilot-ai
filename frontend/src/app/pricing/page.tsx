import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { PublicCTA, PublicSiteLayout } from "@/components/public-site-layout";

const included = [
  "Ticket inbox, customers, and conversation history",
  "Team roles, invitations, and private notes",
  "Knowledge document upload and search",
  "Human-reviewed AI reply drafts",
  "Optional read-only Shopify order lookup",
];

export default function PricingPage() {
  return <PublicSiteLayout><main><section className="border-b border-slate-200 bg-gradient-to-b from-blue-50 to-white"><div className="mx-auto max-w-7xl px-5 py-16 text-center sm:px-8 sm:py-20"><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Pricing</p><h1 className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">Pricing information</h1><p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-slate-600">Public pricing and plan limits aren’t published yet. This page does not imply a price or usage allowance.</p></div></section><section className="mx-auto max-w-4xl px-5 py-14 sm:px-8 sm:py-16"><article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-xl shadow-slate-900/5 sm:p-10"><div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start"><div><span className="rounded-full bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800">Workspace access</span><h2 className="mt-4 text-2xl font-bold">Explore the current product</h2><p className="mt-2 max-w-lg text-sm leading-6 text-slate-600">Review the available capabilities and request a workspace for owner approval.</p></div><Link href="/register" className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-blue-700 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-800">Request a workspace<ArrowRight size={15}/></Link></div><ul className="mt-8 grid gap-3 border-t border-slate-100 pt-6 sm:grid-cols-2">{included.map((item) => <li key={item} className="flex items-start gap-2 text-sm text-slate-700"><Check size={16} className="mt-0.5 shrink-0 text-emerald-600"/>{item}</li>)}</ul><p className="mt-7 rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-500">AI usage cost estimates appear only when the server has input and output token prices configured. Shopify access is optional and read-only.</p></article></section><PublicCTA title="Start with a workspace request" description="Submit your organization details. Workspace access begins after platform-owner approval."/></main></PublicSiteLayout>;
}
