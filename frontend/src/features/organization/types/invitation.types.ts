export type Invitation = {
  id: string;
  email: string;
  role: string;
  invite_token?: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
};
