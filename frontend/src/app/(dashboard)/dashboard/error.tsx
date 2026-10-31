"use client";

export default function DashboardError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div role="alert" className="rounded-2xl border border-red-200 bg-red-50 p-6">
      <h2 className="font-semibold text-red-900">This page could not load</h2>
      <p className="mt-1 text-sm text-red-800">Try again. If the problem continues, refresh your workspace.</p>
      <button className="mt-4 rounded-lg bg-red-800 px-4 py-2 text-sm font-semibold text-white" onClick={() => reset()}>Try again</button>
    </div>
  );
}
