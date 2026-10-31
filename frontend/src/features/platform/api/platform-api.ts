import { api } from "@/lib/api/client";
import type { PlatformLoginValues } from "../schemas/platform-auth.schema";
import type { Page, PlatformOwner, TenantReview } from "../types/platform.types";

export const platformOwnerQueryKey = ["platform-owner"] as const;
export const tenantReviewQueryKey = (status: string) => ["platform-tenants", status] as const;

export const platformLogin = (values: PlatformLoginValues) =>
  api<{ platform_owner: PlatformOwner }>("/platform/auth/login", {
    method: "POST",
    body: JSON.stringify(values),
  });
export const getPlatformOwner = () => api<PlatformOwner>("/platform/auth/me");
export const platformLogout = () => api<void>("/platform/auth/logout", { method: "POST" });
export const listTenantReviews = (status: string) =>
  api<Page<TenantReview>>(`/platform/tenants?approval_status=${encodeURIComponent(status)}`);

export function reviewTenant(id: string, action: "approve" | "reject" | "reopen") {
  return api<TenantReview>(`/platform/tenants/${encodeURIComponent(id)}/${action}`, { method: "POST" });
}
