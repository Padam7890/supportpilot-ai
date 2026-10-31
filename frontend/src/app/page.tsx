export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 p-10 shadow-2xl">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-xl font-bold">
            S
          </div>

          <div>
            <h2 className="text-lg font-semibold">SupportPilot AI</h2>
            <p className="text-xs text-slate-400">
              Intelligent customer support platform
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <p className="text-sm font-medium text-blue-400">
            SPRINT 1 · PROJECT FOUNDATION
          </p>

          <h1 className="text-4xl font-bold tracking-tight">
            Your AI support operations start here.
          </h1>

          <p className="leading-7 text-slate-400">
            A production-oriented AI customer support platform built with
            FastAPI, LangGraph, Next.js and PostgreSQL.
          </p>

          <div className="flex flex-wrap gap-2 pt-4">
            {["FastAPI", "Next.js", "PostgreSQL", "pgvector", "Redis"].map(
              (technology) => (
                <span
                  key={technology}
                  className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300"
                >
                  {technology}
                </span>
              ),
            )}
          </div>

          <div className="border-t border-slate-800 pt-5">
            <p className="text-sm text-emerald-400">
              ● Frontend application initialized
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}
