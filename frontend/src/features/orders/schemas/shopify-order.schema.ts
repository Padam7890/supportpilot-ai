import { z } from "zod";

export const shopifyLookupSchema = z.object({
  customer_email: z.email("Enter a valid customer email."),
  order_number: z.string().trim().min(1, "Enter the order number.").max(60).regex(/^#?[A-Za-z0-9-]+$/, "Use the Shopify order number, for example #1042."),
});

export type ShopifyLookupValues = z.infer<typeof shopifyLookupSchema>;
