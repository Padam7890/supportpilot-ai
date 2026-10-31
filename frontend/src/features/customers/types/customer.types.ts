export type Customer = {
  id: string;
  organization_id: string;
  name: string;
  email: string;
  phone: string | null;
  external_reference: string | null;
  created_at: string;
  updated_at: string;
};
