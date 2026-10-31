import { z } from "zod";

export const sendMessageSchema = z.object({ content: z.string().trim().min(1).max(20000) });
export type SendMessageValues = z.infer<typeof sendMessageSchema>;
