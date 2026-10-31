import { z } from "zod";

export const createCustomerSchema = z.object({
  name: z.string().min(1).max(160),
  email: z.email(),
  phone: z.string().max(40).optional(),
  external_reference: z.string().max(120).optional(),
});

export const updateCustomerSchema = z.object({
  name: z.string().min(1).max(160),
  email: z.email(),
  phone: z.string().max(40),
  external_reference: z.string().max(120),
});
