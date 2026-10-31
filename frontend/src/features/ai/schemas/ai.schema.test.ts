import { describe, expect, it } from "vitest";
import { playgroundSchema, replyDraftSchema } from "./ai.schema";

describe("AI request schemas", () => {
  it("trims a valid playground question and rejects whitespace only", () => {
    expect(playgroundSchema.parse({ question: "  What is the return policy?  " }).question).toBe(
      "What is the return policy?",
    );
    expect(playgroundSchema.safeParse({ question: "    " }).success).toBe(false);
  });

  it("requires an explicit conversation id for inbox drafts", () => {
    expect(replyDraftSchema.safeParse({ conversation_id: "not-a-uuid" }).success).toBe(false);
    expect(replyDraftSchema.safeParse({ conversation_id: "a6b6b3aa-2337-494d-9cf6-fd82e15fb35c" }).success).toBe(true);
  });
});
