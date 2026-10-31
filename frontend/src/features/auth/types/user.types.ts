export type User = {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "agent" | "viewer";
  is_active: boolean;
  organization?: { id: string; name: string; slug: string };
};
