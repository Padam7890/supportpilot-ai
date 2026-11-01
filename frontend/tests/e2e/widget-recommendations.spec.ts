import { expect, test } from "@playwright/test";

test("recommendation cards remain readable on mobile and support keyboard and compare actions", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.setContent('<main><div id="recommendations"></div><output id="selection"></output></main>');
  await page.addScriptTag({ url: `${baseURL}/supportpilot-recommendations.js` });
  await page.evaluate(() => {
    const ui = (window as Window & { SupportPilotRecommendationUI?: {
      mountStyles(shadow: ShadowRoot): void;
      ProductRecommendationMessage(payload: Record<string, unknown>, options: {
        onCompare(index: number, reference: { product_id: string; variant_id: string }): boolean;
        getCompareCount(): number;
        onCompareSelected(): void;
      }): HTMLElement;
    } }).SupportPilotRecommendationUI;
    if (!ui) throw new Error("Recommendation renderer unavailable");
    const host = document.createElement("div");
    const shadow = host.attachShadow({ mode: "open" });
    ui.mountStyles(shadow);
    const selected = new Set<string>();
    const section = ui.ProductRecommendationMessage({
      response_type: "recommendations",
      explanation: "Options matching your request.",
      available_actions: ["view_product", "refine_search"],
      products: [1, 2, 3, 4].map((number) => ({
        product_id: `product-${number}`,
        variant_id: `variant-${number}`,
        title: `Phone ${number}`,
        price: "25000",
        currency: "NPR",
        availability: "available",
        product_url: `https://store.example/products/${number}`,
        reasons: ["Verified catalog feature match"],
        verified_attributes: { camera: `${number * 10} MP` },
        limitations: [],
      })),
    }, {
      onCompare: (index, reference) => {
        if (selected.has(reference.product_id)) {
          selected.delete(reference.product_id);
          return false;
        }
        selected.add(reference.product_id);
        const output = document.querySelector("#selection");
        if (output) output.textContent += `${index + 1},`;
        return true;
      },
      getCompareCount: () => selected.size,
      onCompareSelected: () => {
        const output = document.querySelector("#selection");
        if (output) output.textContent += "compare";
      },
    });
    shadow.appendChild(section);
    const mount = document.querySelector("#recommendations");
    if (mount) mount.appendChild(host);
  });
  const frame = page.locator("#recommendations > div");
  await expect(page.locator("#recommendations")).toContainText("Options matching your request.");
  await expect(page.locator("#recommendations")).toContainText("Phone 1");
  const viewport = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, content: document.body.scrollWidth }));
  expect(viewport.content).toBeLessThanOrEqual(viewport.viewport);
  await frame.evaluate((host) => {
    const root = host.shadowRoot;
    const cards = root?.querySelectorAll(".recommendation-card");
    cards?.[0].querySelector("button[aria-label^='Add to compare']")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    cards?.[1].querySelector("button[aria-label^='Add to compare']")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    root?.querySelector(".recommendation-compare-submit")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect(page.locator("#selection")).toHaveText("1,2,compare");
  await expect(frame.locator(".recommendation-track")).toHaveAttribute("tabindex", "0");
  await expect(frame.locator("a[rel='noopener noreferrer']")).toHaveCount(4);
  await expect(page.locator(".recommendation-card")).toHaveCount(4);
});
