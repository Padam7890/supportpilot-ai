export type PlatformOwner = { id: string; email: string };

export type TenantReview = {
  id: string;
  name: string;
  slug: string;
  approval_status: "pending" | "approved" | "rejected";
  created_at: string;
  reviewed_at: string | null;
  reviewed_by_platform_owner_id: string | null;
  requester_name: string | null;
  requester_email: string | null;
};

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };
