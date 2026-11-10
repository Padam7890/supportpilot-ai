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
    let historyReady = false;
    window.addEventListener("commit-history", () => { historyReady = true; });
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
            if (resumed) {
              push("message.delta", firstCursor, { text: "**Shipping** " });
            }
            push("message.delta", resumed ? `${executionId}:1:124-0` : firstCursor, {
              text: resumed ? "takes **two" : "**Shipping** ",
            });
            if (resumed) {
              window.addEventListener("next-provider-chunk", () => {
                push("message.delta", `${executionId}:1:125-0`, { text: " days**." });
              }, { once: true });
            }
            window.addEventListener(resumed ? "commit-reply" : "drop-connection", () => {
              if (resumed) {
                completed = true;
                push("message.delta", `${executionId}:1:126-0`, {
                  text: "\n\n- Standard delivery\n- <img src=x onerror=alert(1)>",
                });
                push("message.completed", `${executionId}:1:999-0`, { message_id: "final" });
              }
              controller.close();
            }, { once: true });
          },
        });
        return new Response(stream, { headers: { "content-type": "text/event-stream" } });
      }
      if (url.pathname.endsWith(conversationId)) {
        if (completed && !historyReady) performance.mark("test-history-pending");
        return Response.json({ ai_mode: "ai", messages: [
          ...(sent ? [{ id: "customer", sender_type: "customer", content: question, created_at: date }] : []),
          ...(completed && historyReady ? [{ id: "final", sender_type: "assistant", content: "Shipping takes **two days**.\n\n- Standard delivery\n- <img src=x onerror=alert(1)>", created_at: date }] : []),
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
  const firstPaint = await page.evaluate(() =>
    performance.getEntriesByType("mark").find((mark) => mark.name.endsWith(":first_dom_update"))?.startTime
  );
  expect(firstPaint).toBeDefined();
  await page.evaluate(() => window.dispatchEvent(new Event("drop-connection")));
  await expect(partial).toHaveText("Shipping takes two");
  await page.evaluate(() => window.dispatchEvent(new Event("next-provider-chunk")));
  await expect(partial).toHaveText("Shipping takes two days.");
  const firstChunk = await page.evaluate(() =>
    performance.getEntriesByType("mark").find((mark) => mark.name.endsWith(":first_browser_delta"))?.startTime
  );
  expect(firstChunk).toBeDefined();
  console.log("browser first chunk to first DOM update (ms)", Math.round(Number(firstPaint) - Number(firstChunk)));
  await widget.evaluate((host) => {
    const thread = host.shadowRoot?.querySelector(".thread");
    const lengths = new Set<number>();
    if (!thread) throw new Error("Widget thread unavailable");
    const observer = new MutationObserver(() => {
      const text = thread.querySelector(".streaming-row .message")?.textContent;
      if (text) lengths.add(text.length);
      host.setAttribute("data-burst-paints", String(lengths.size));
    });
    observer.observe(thread, { subtree: true, childList: true });
  });
  await page.evaluate(() => window.dispatchEvent(new Event("commit-reply")));
  await expect.poll(() => page.evaluate(() =>
    performance.getEntriesByName("test-history-pending").length
  )).toBeGreaterThan(0);
  await expect(partial).toContainText("Shipping takes two days.");
  await expect.poll(async () => Number(await widget.getAttribute("data-burst-paints"))).toBeGreaterThan(2);
  // The browser must paint several intermediate lengths even when the final
  // network burst contains most of the response in a single read.
  const observedPaints = Number(await widget.getAttribute("data-burst-paints"));
  expect(observedPaints).toBeGreaterThan(2);
  await page.evaluate(() => window.dispatchEvent(new Event("commit-history")));
  await expect(widget.locator(".assistant .message")).toHaveCount(1);
  const reply = widget.locator(".assistant:not(.streaming-row) .message");
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

test("widget hides the order card when verification is paused and restores it after recovery", async ({ page, baseURL }) => {
  const conversationId = "00000000-0000-4000-8000-000000000001";
  let recovered = false;
  await page.addInitScript(({ id }) => {
    const attach = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (options) {
      return attach.call(this, { ...options, mode: "open" });
    };
    sessionStorage.setItem("supportpilot-widget-session:order-test", JSON.stringify({
      conversation_id: id, visitor_token: "test-token",
    }));
  }, { id: conversationId });
  await page.route("**/api/widget/order-test/config", (route) => route.fulfill({
    json: { ai_enabled: true, streaming_enabled: false },
  }));
  await page.route(`**/api/widget/conversations/${conversationId}`, (route) => route.fulfill({
    json: { ai_mode: "ai", order_verified: false, messages: [
      { id: "customer", sender_type: "customer", content: "I forget the order number" },
      {
        id: recovered ? "resume" : "pause",
        sender_type: "assistant",
        content: recovered ? "Use the secure verification card." : "Check your confirmation email. Would you like the store team to help?",
        verification_required: recovered,
        verification_paused: !recovered,
      },
      ...(!recovered ? [{ id: "follow-up", sender_type: "customer", content: "What is my order status?" }] : []),
    ] },
  }));
  await page.route("**/storefront-order-fixture", (route) => route.fulfill({
    contentType: "text/html",
    body: '<script defer src="/supportpilot-widget.js" data-widget-id="order-test" data-api-base="/api"></script>',
  }));
  const openWidget = async () => {
    await page.goto(`${baseURL}/storefront-order-fixture`);
    const widget = page.locator("#supportpilot-widget-host");
    await widget.locator(".launcher").click();
    return widget;
  };
  const paused = await openWidget();
  await expect(paused.getByText("Check your confirmation email.", { exact: false })).toBeVisible();
  await expect(paused.getByRole("heading", { name: "Verify your order" })).toHaveCount(0);

  recovered = true;
  const resumed = await openWidget();
  await expect(resumed.getByRole("heading", { name: "Verify your order" })).toBeVisible();
});
