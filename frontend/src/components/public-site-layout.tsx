import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowRight, Sparkles } from "lucide-react";

const COPYRIGHT_YEAR = 2026;

export function PublicSiteLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-white text-slate-950">
    <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur">
      <nav aria-label="Main navigation" className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
        <Link href="/" className="flex items-center gap-2.5 rounded-lg font-bold tracking-tight"><span className="grid size-9 place-items-center rounded-xl bg-blue-700 text-white"><Sparkles size={18}/></span>SupportPilot AI</Link>
        <div className="hidden items-center gap-7 text-sm font-medium text-slate-600 sm:flex"><Link href="/features" className="hover:text-blue-700">Features</Link><Link href="/pricing" className="hover:text-blue-700">Pricing</Link></div>
        <div className="flex items-center gap-2"><Link href="/login" className="rounded-lg px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-100">Log in</Link><Link href="/register" className="inline-flex items-center gap-2 rounded-lg bg-blue-700 px-3.5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-800">Request a workspace<ArrowRight size={15}/></Link></div>
      </nav>
    </header>
    {children}
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-8 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between sm:px-8"><p>© {COPYRIGHT_YEAR} SupportPilot AI</p><nav aria-label="Footer navigation" className="flex gap-5"><Link href="/features" className="hover:text-blue-700">Features</Link><Link href="/pricing" className="hover:text-blue-700">Pricing</Link><Link href="/login" className="hover:text-blue-700">Workspace login</Link></nav></div>
    </footer>
  </div>;
}

export function PublicCTA({ title = "Bring your support work into one workspace", description = "Request a workspace and a platform owner will review your registration." }: { title?: string; description?: string }) {
  return <section className="mx-auto max-w-7xl px-5 pb-20 sm:px-8"><div className="rounded-3xl bg-slate-950 px-6 py-10 text-white sm:px-10 sm:py-12"><div className="max-w-2xl"><h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h2><p className="mt-3 text-sm leading-6 text-slate-300">{description}</p><Link href="/register" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-blue-700 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-800">Request a workspace<ArrowRight size={16}/></Link><p className="mt-3 text-xs text-slate-400">New workspaces require platform-owner approval before sign-in.</p></div></div></section>;
}
