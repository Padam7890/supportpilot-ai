import { SecuritySessions } from "@/features/auth/components/security-sessions";

export default function SecurityPage() {
  return <div className="mx-auto max-w-5xl space-y-6"><header><p className="text-xs font-bold uppercase tracking-[.16em] text-blue-700">Account protection</p><h1 className="mt-1 text-3xl font-bold tracking-tight">Security</h1><p className="mt-2 text-sm text-slate-500">Manage refresh access for your own workspace account.</p></header><SecuritySessions/></div>;
}
