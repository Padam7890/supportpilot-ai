import { z } from "zod";

export const loginSchema = z.object({
  organization_slug: z.string().min(3, "Enter your organization slug"),
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export const registerSchema = z.object({
  organization_name: z.string().min(2).max(160),
  organization_slug: z.string().min(3).max(80).regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Use lowercase letters, numbers, and hyphens"),
  full_name: z.string().min(2).max(160),
  email: z.email("Enter a valid email address"),
  password: z.string().min(12, "Use at least 12 characters").max(128),
});

export const inviteAcceptanceSchema = z.object({
  full_name: z.string().min(2).max(160),
  password: z.string().min(12).max(128),
});

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type InviteAcceptanceValues = z.infer<typeof inviteAcceptanceSchema>;
