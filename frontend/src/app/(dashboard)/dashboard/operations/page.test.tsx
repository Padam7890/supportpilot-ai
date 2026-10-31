import { cleanup, render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/errors";
import OperationsPage from "./page";

const { getSystemReadiness } = vi.hoisted(() => ({ getSystemReadiness: vi.fn() }));

vi.mock("@/features/dashboard/api/system-status-api", () => ({ getSystemReadiness }));

afterEach(() => cleanup());

describe("Operations readiness failures", () => {
  it("shows the actionable database migration error returned by the API", async () => {
    getSystemReadiness.mockRejectedValueOnce(new ApiError(
      "Database schema migrations are not current. Apply the latest Alembic migrations.",
      503,
      { code: "service_unavailable" },
    ));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = render(<QueryClientProvider client={client}><OperationsPage/></QueryClientProvider>);

    expect(await view.findByText("Database schema migrations are not current. Apply the latest Alembic migrations.")).toBeInTheDocument();
  });
});
