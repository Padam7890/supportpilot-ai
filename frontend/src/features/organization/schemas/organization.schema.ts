import { z } from "zod";

export const inviteSchema = z.object({ email: z.email(), role: z.enum(["admin", "agent", "viewer"]) });
export const organizationSchema = z.object({ name: z.string().min(2).max(160) });
export type InviteValues = z.infer<typeof inviteSchema>;
export type OrganizationValues = z.infer<typeof organizationSchema>;
