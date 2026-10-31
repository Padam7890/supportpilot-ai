import { z } from "zod";

export const platformLoginSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export type PlatformLoginValues = z.infer<typeof platformLoginSchema>;
