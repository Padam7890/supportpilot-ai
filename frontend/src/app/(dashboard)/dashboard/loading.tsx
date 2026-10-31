export default function DashboardLoading() {
  return (
    <div aria-label="Loading dashboard" className="space-y-6">
      <div className="h-24 animate-pulse rounded-2xl bg-white" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[1, 2, 3, 4].map((item) => <div key={item} className="h-32 animate-pulse rounded-2xl bg-white" />)}
      </div>
      <div className="h-80 animate-pulse rounded-2xl bg-white" />
    </div>
  );
}
