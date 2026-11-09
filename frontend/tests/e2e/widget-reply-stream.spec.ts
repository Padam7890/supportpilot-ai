import { expect, test } from "@playwright/test";

test("widget renders a partial reply, resumes after disconnect, and keeps one final message", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => {
    // Open the isolated tree for assertions against the production widget script.
    const attach = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (options) {
      return attach.call(this, { ...options, mode: "open" });
    };

    const originalFetch = window.fetch.bind(window);
    const conversationId = "00000000-0000-4000-8000-000000000001";
    const executionId = "00000000-0000-4000-8000-000000000002";
    const firstCursor = `${executionId}:1:123-0`;
    const question = "What is the shipping policy?";
    let sent = false;
    let completed = false;
    const date = new Date().toISOString();

    window.fetch = async (input, options) => {
      const url = new URL(String(input), location.href);
      if (url.pathname.endsWith("/config")) {
        return Response.json({ ai_enabled: true, streaming_enabled: true });
      }
      if (url.pathname.endsWith("/messages")) {
        await new Promise<void>((resolve) => window.addEventListener("allow-ack", () => resolve(), { once: true }));
        sent = true;
        return Response.json({ conversation_id: conversationId, visitor_token: "test-token" });
      }
      if (url.pathname.endsWith("/reply-stream")) {
        const resumed = url.searchParams.get("after") === firstCursor;
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            const push = (eventType: string, sequence: string, payload: object) => controller.enqueue(
              new TextEncoder().encode(`data: ${JSON.stringify({
                execution_id: executionId, conversation_id: conversationId,
                sequence, event_type: eventType, timestamp: date, payload,
              })}\n\n`),
            );
            push("message.delta", resumed ? `${executionId}:1:124-0` : firstCursor, {
              text: resumed ? "takes **two" : "**Shipping** ",
            });
            if (resumed) {
              push("message.delta", `${executionId}:1:125-0`, { text: " days**." });
            }
            window.addEventListener(resumed ? "commit-reply" : "drop-connection", () => {
              if (resumed) {
                completed = true;
                push("message.completed", `${executionId}:1:999-0`, { message_id: "final" });
              }
              controller.close();
            }, { once: true });
          },
        });
        return new Response(stream, { headers: { "content-type": "text/event-stream" } });
      }
      if (url.pathname.endsWith(conversationId)) {
        return Response.json({ ai_mode: "ai", messages: [
          ...(sent ? [{ id: "customer", sender_type: "customer", content: question, created_at: date }] : []),
          ...(completed ? [{ id: "final", sender_type: "assistant", content: "Shipping takes **two days**.\n\n- Standard delivery\n- <img src=x onerror=alert(1)>", created_at: date }] : []),
        ] });
      }
      return originalFetch(input, options);
    };
  });
  await page.route("**/storefront-stream-fixture", (route) => route.fulfill({
    contentType: "text/html",
    body: '<script defer src="/supportpilot-widget.js" data-widget-id="stream-test" data-api-base="/api"></script>',
  }));
  await page.goto(`${baseURL}/storefront-stream-fixture`);
  const widget = page.locator("#supportpilot-widget-host");
  await widget.locator(".launcher").click();
  await widget.getByRole("textbox", { name: "Message the support assistant" }).fill("What is the shipping policy?");
  await widget.getByRole("button", { name: "Send message" }).click();
  await expect(widget.locator(".customer .message")).toHaveText("What is the shipping policy?");
  await page.evaluate(() => window.dispatchEvent(new Event("allow-ack")));
  const partial = widget.locator(".streaming-row .message");
  await expect(partial.locator("strong")).toHaveText("Shipping");
  await widget.evaluate((host) => {
    const thread = host.shadowRoot?.querySelector(".thread");
    if (!thread) throw new Error("Widget thread unavailable");
    const observer = new MutationObserver(() => {
      if (thread.querySelector(".streaming-row .message")?.textContent === "Shipping takes two") {
        host.setAttribute("data-painted-intermediate", "true");
        observer.disconnect();
      }
    });
    observer.observe(thread, { subtree: true, childList: true });
    window.dispatchEvent(new Event("drop-connection"));
  });
  await expect(partial).toHaveText("Shipping takes two days.");
  await expect(widget).toHaveAttribute("data-painted-intermediate", "true");
  await page.evaluate(() => window.dispatchEvent(new Event("commit-reply")));
  await expect(widget.locator(".assistant .message")).toHaveCount(1);
  const reply = widget.locator(".assistant .message");
  await expect(reply.locator("strong")).toHaveText("two days");
  await expect(reply.locator("ul li")).toHaveCount(2);
  await expect(reply.locator("ul li").last()).toHaveText("<img src=x onerror=alert(1)>");
  await expect(reply.locator("img")).toHaveCount(0);
  await expect(partial).toHaveCount(0);
  await expect(widget.locator(".customer .message")).toHaveCount(1);
});

test("idle widget loads history once, refreshes after 30 seconds, and stops on close", async ({ page, baseURL }) => {
  const conversationId = "00000000-0000-4000-8000-000000000001";
  let historyRequests = 0;
  let streamRequests = 0;
  await page.clock.install();
  await page.addInitScript(({ id }) => {
    const attach = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (options) {
      return attach.call(this, { ...options, mode: "open" });
    };
    sessionStorage.setItem("supportpilot-widget-session:stream-test", JSON.stringify({
      conversation_id: id,
      visitor_token: "test-token",
    }));
  }, { id: conversationId });
  await page.route("**/api/widget/stream-test/config", (route) => route.fulfill({
    json: { ai_enabled: true, streaming_enabled: true },
  }));
  await page.route(`**/api/widget/conversations/${conversationId}`, (route) => {
    historyRequests++;
    return route.fulfill({ json: { ai_mode: "ai", messages: [] } });
  });
  await page.route("**/reply-stream", (route) => {
    streamRequests++;
    return route.fulfill({ contentType: "text/event-stream", body: "" });
  });
  await page.route("**/storefront-poll-fixture", (route) => route.fulfill({
    contentType: "text/html",
    body: '<script defer src="/supportpilot-widget.js" data-widget-id="stream-test" data-api-base="/api"></script>',
  }));
  await page.goto(`${baseURL}/storefront-poll-fixture`);
  const widget = page.locator("#supportpilot-widget-host");
  await widget.locator(".launcher").click();
  await expect(widget.getByRole("heading", { name: "Hi! Welcome to our store." })).toBeVisible();
  expect(historyRequests).toBe(1);
  expect(streamRequests).toBe(0);

  await page.clock.fastForward(6_000);
  expect(historyRequests).toBe(1);
  await page.clock.fastForward(25_000);
  await expect.poll(() => historyRequests).toBe(2);
  await widget.getByRole("button", { name: "Close support chat" }).click();
  await page.clock.fastForward(65_000);
  expect(historyRequests).toBe(2);
  expect(streamRequests).toBe(0);
});
