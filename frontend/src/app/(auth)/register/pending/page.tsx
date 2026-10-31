import Link from "next/link";

export default function RegistrationPendingPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-10">
      <section className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/50">
        <span className="flex size-11 items-center justify-center rounded-2xl bg-amber-100 text-xl">⌛</span>
        <p className="mt-6 text-xs font-bold uppercase tracking-[0.16em] text-amber-700">Approval pending</p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">Your workspace is awaiting review</h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Your workspace registration has been submitted for approval. A SupportPilot platform owner must approve it before you can sign in.
        </p>
        <p className="mt-3 text-sm text-slate-500">You can return to this page later and try signing in to check your approval status.</p>
        <Link href="/login" className="mt-6 inline-flex rounded-xl bg-blue-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-800">Go to sign in</Link>
      </section>
    </main>
  );
}
