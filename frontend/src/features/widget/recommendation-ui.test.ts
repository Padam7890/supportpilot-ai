import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

type RecommendationRenderer = {
  mountStyles(shadow: ShadowRoot): void;
  ProductRecommendationMessage(
    payload: Record<string, unknown>,
    options?: {
      onCompare?: (index: number, reference: { product_id: string; variant_id: string }) => boolean | void;
      onQuickReply?: (reply: string) => void;
      selectedCompareProductIds?: string[];
      getCompareCount?: () => number;
      onCompareSelected?: () => void;
    },
  ): HTMLElement;
  RecommendationEmptyState(message: string): HTMLElement;
  RecommendationErrorState(message: string): HTMLElement;
  RecommendationLoadingState(): HTMLElement;
  RecommendationQuickReplies(replies: string[], onSelect: (reply: string) => void): HTMLElement;
};

declare global {
  interface Window {
    SupportPilotRecommendationUI?: RecommendationRenderer;
  }
}

const source = readFileSync(resolve(process.cwd(), "public/supportpilot-recommendations.js"), "utf8");

function loadRenderer() {
  new Function("window", "document", source)(window, document);
  if (!window.SupportPilotRecommendationUI) throw new Error("Renderer did not initialize");
  return window.SupportPilotRecommendationUI;
}

describe("storefront recommendation presentation", () => {
  beforeEach(() => {
    document.body.replaceChildren();
    delete window.SupportPilotRecommendationUI;
  });

  it("renders grounded product facts and safe external detail links", () => {
    const ui = loadRenderer();
    const shadowHost = document.createElement("div");
    const shadow = shadowHost.attachShadow({ mode: "open" });
    ui.mountStyles(shadow);
    let comparedIndex = -1;
    const result = ui.ProductRecommendationMessage({
      response_type: "recommendations",
      explanation: "Matched your phone budget.",
      available_actions: ["view_product", "refine_search"],
      limitations: ["Availability is based on the latest catalog sync."],
      suggested_follow_ups: ["Compare the first two"],
      products: [{
        title: "<img src=x onerror=alert(1)>",
        price: "29999.00",
        currency: "NPR",
        availability: "available",
        image_url: "javascript:alert(1)",
        product_url: "https://store.example/products/phone",
        reasons: ["Catalog information mentions camera"],
        verified_attributes: { camera: "50 MP" },
        limitations: [],
        variant_id: "variant-1",
        variant_title: "Blue, 128 GB",
        variant_options: [
          { variant_id: "variant-1", variant_title: "Blue, 128 GB", price: "29999.00", currency: "NPR", availability: "available", verified_attributes: { camera: "50 MP" }, reasons: ["Catalog information mentions camera"], limitations: [] },
          { variant_id: "variant-2", variant_title: "Black, 256 GB", price: "31999.00", currency: "NPR", availability: "available", verified_attributes: { battery: "5000 mAh" }, reasons: ["Catalog information matches the preference battery"], limitations: [] },
        ],
      }],
    }, { onCompare: (index) => { comparedIndex = index; } });
    shadow.appendChild(result);
    expect(shadow.textContent).toContain("Matched your phone budget.");
    expect(shadow.textContent).toContain("camera: 50 MP");
    expect(shadow.querySelector("img")).toBeNull();
    expect(shadow.querySelector("a")?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(shadow.querySelector("button[aria-label^='Add to compare']")).toBeTruthy();
    const variant = shadow.querySelector("select[aria-label^='Variant']");
    expect(variant).toBeTruthy();
    if (variant instanceof HTMLSelectElement) {
      variant.value = "variant-2";
      variant.dispatchEvent(new Event("change", { bubbles: true }));
    }
    expect(shadow.querySelector(".recommendation-price")?.textContent).toContain("31,999");
    expect(shadow.textContent).toContain("battery: 5000 mAh");
    shadow.querySelector("button[aria-label^='Add to compare']")?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(comparedIndex).toBe(0);
    expect(shadow.textContent).not.toContain("Add to cart");
  });

  it("provides comparison, empty, error, quick-reply and loading states accessibly", () => {
    const ui = loadRenderer();
    const comparison = ui.ProductRecommendationMessage({
      response_type: "comparison",
      explanation: "Verified comparison.",
      products: [
        { title: "Phone A", price: "100", currency: "NPR", availability: "available", brand: "A", verified_attributes: { camera: "12 MP" }, normalized_attributes: { camera: "12 MP" } },
        { title: "Phone B", price: "120", currency: "NPR", availability: "unknown", brand: "B", verified_attributes: { battery: "5 Ah" }, normalized_attributes: { battery: "5,000 mAh (catalog: 5 Ah)" } },
      ],
      differences: ["Price differs"],
      trade_offs: ["For your battery priority, the catalog lists Phone A: not listed; Phone B: 5,000 mAh."],
    });
    expect(comparison.querySelector("table")).toBeTruthy();
    expect(comparison.textContent).toContain("Not listed");
    expect(comparison.textContent).toContain("5,000 mAh");
    expect(comparison.textContent).toContain("battery priority");
    expect(ui.RecommendationEmptyState("No matching products.").getAttribute("role")).toBe("status");
    expect(ui.RecommendationErrorState("Temporary failure").getAttribute("role")).toBe("alert");
    expect(ui.RecommendationLoadingState().getAttribute("role")).toBe("status");
    let selected = "";
    ui.RecommendationQuickReplies(["Compare the first two"], (value: string) => { selected = value; })
      .querySelector("button")?.click();
    expect(selected).toBe("Compare the first two");
  });

  it("supports choosing up to four products before starting comparison", () => {
    const ui = loadRenderer();
    const selected = new Set<string>();
    let compared = false;
    const section = ui.ProductRecommendationMessage({
      response_type: "recommendations",
      products: [1, 2, 3, 4].map((number) => ({
        product_id: `product-${number}`,
        variant_id: `variant-${number}`,
        title: `Phone ${number}`,
        price: "100",
        currency: "NPR",
        availability: "available",
        verified_attributes: {},
      })),
    }, {
      selectedCompareProductIds: [],
      getCompareCount: () => selected.size,
      onCompare: (_index: number, reference: { product_id: string }) => {
        if (selected.has(reference.product_id)) {
          selected.delete(reference.product_id);
          return false;
        }
        selected.add(reference.product_id);
        return true;
      },
      onCompareSelected: () => { compared = true; },
    });
    const host = document.createElement("div");
    host.attachShadow({ mode: "open" }).appendChild(section);
    const shadow = host.shadowRoot;
    const compareButtons = shadow?.querySelectorAll("button[aria-label^='Add to compare']");
    expect(compareButtons).toHaveLength(4);
    compareButtons?.[0].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    compareButtons?.[1].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    compareButtons?.[2].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    compareButtons?.[3].dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(shadow?.querySelector(".recommendation-compare-submit")?.textContent).toBe("Compare selected (4)");
    (shadow?.querySelector(".recommendation-compare-submit") as HTMLButtonElement).click();
    expect(compared).toBe(true);
  });
});
