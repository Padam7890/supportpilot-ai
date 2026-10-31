import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-50 px-4 text-center">
      <div><p className="text-sm font-semibold text-blue-700">404</p><h1 className="mt-2 text-3xl font-bold">Page not found</h1><p className="mt-2 text-slate-600">The page may have moved or the link may be incorrect.</p><Link href="/" className="mt-5 inline-block font-semibold text-blue-700">Return to SupportPilot</Link></div>
    </main>
  );
}
