import { z } from "zod";

export const playgroundSchema = z.object({
  question: z.string().trim().min(4, "Enter a question with at least 4 characters.").max(2000),
});

export const replyDraftSchema = z.object({
  conversation_id: z.string().uuid(),
  instructions: z.string().trim().max(500).optional(),
  shopify_order_number: z.string().trim().min(1).max(60).regex(/^#?[A-Za-z0-9-]+$/).optional(),
});
