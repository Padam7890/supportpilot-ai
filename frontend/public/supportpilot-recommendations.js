(() => {
  const safeExternalUrl = (value) => {
    if (typeof value !== "string") return null;
    try {
      const url = new URL(value);
      return url.protocol === "https:" ? url.href : null;
    } catch {
      return null;
    }
  };

  const textElement = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = String(value ?? "");
    return node;
  };

  const priceLabel = (value, currency) => {
    const amount = Number(value);
    if (!Number.isFinite(amount) || !/^[A-Z]{3}$/.test(currency || "")) return `${value} ${currency || ""}`.trim();
    try {
      return new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
    } catch {
      return `${amount.toLocaleString()} ${currency}`;
    }
  };

  function mountStyles(shadow) {
    if (shadow.querySelector("#supportpilot-recommendation-styles")) return;
    const style = document.createElement("style");
    style.id = "supportpilot-recommendation-styles";
    style.textContent = `
      .recommendation-message{width:100%;min-width:0;max-width:100%;gap:7px}
      .recommendation-message,.recommendation-message *{box-sizing:border-box}
      .recommendation-intro{width:100%;border:1px solid #dfe6f2;border-radius:15px;background:#fff;padding:11px 13px;color:#25334d;font-size:12px;line-height:1.55}
      .recommendation-carousel{position:relative;width:100%;min-width:0}
      .recommendation-track{display:grid;grid-auto-columns:minmax(205px,74%);grid-auto-flow:column;gap:10px;overflow-x:auto;overscroll-behavior-inline:contain;scroll-snap-type:x mandatory;padding:2px 1px 9px;scrollbar-width:thin}
      .recommendation-card{display:flex;min-width:0;flex-direction:column;overflow:hidden;scroll-snap-align:start;border:1px solid #dfe6f2;border-radius:15px;background:#fff;box-shadow:0 3px 12px #17233b0c}
      .recommendation-image-wrap{display:grid;height:130px;place-items:center;overflow:hidden;background:#f1f5fb;color:#7b879a;font-size:11px}
      .recommendation-image{width:100%;height:100%;object-fit:cover}
      .recommendation-body{display:flex;flex:1;flex-direction:column;gap:7px;padding:11px}
      .recommendation-title{margin:0;color:#1d2c48;font-size:13px;font-weight:750;line-height:1.4}
      .recommendation-price{color:#1e3a8a;font-size:14px;font-weight:800}
      .recommendation-variant-label{display:grid;gap:4px;color:#58667b;font-size:10px;font-weight:650}
      .recommendation-variant-select{width:100%;min-height:34px;border:1px solid #d7e0ef;border-radius:8px;background:#fff;padding:6px 8px;color:#30415f;font-size:10px}
      .recommendation-status{width:max-content;border-radius:999px;background:#ecfdf3;padding:3px 8px;color:#13734a;font-size:10px;font-weight:700}
      .recommendation-status.unknown{background:#f1f5f9;color:#58667b}.recommendation-status.unavailable{background:#fff1f2;color:#b42336}
      .recommendation-reason,.recommendation-limitation{margin:0;color:#58667b;font-size:10px;line-height:1.45}
      .recommendation-attrs{display:flex;flex-wrap:wrap;gap:5px;margin:0;padding:0;list-style:none}
      .recommendation-attrs li{border-radius:7px;background:#f1f5fb;padding:4px 6px;color:#40516d;font-size:9px}
      .recommendation-actions{display:flex;gap:7px;margin-top:auto;padding-top:2px}
      .recommendation-action,.recommendation-nav,.recommendation-quick-reply{min-height:32px;border:1px solid #d7e0ef;border-radius:9px;background:#fff;padding:6px 9px;color:#30415f;font-size:10px;font-weight:700;text-decoration:none}
      .recommendation-action.primary{border-color:#3158d8;background:#3158d8;color:#fff}
      .recommendation-action:disabled{cursor:not-allowed;opacity:.55}
      .recommendation-action:focus-visible,.recommendation-nav:focus-visible,.recommendation-quick-reply:focus-visible{outline:3px solid #f6c945;outline-offset:2px}
      .recommendation-nav{position:absolute;top:43%;z-index:1;display:grid;width:29px;min-height:29px;place-items:center;border-radius:50%;padding:0;box-shadow:0 2px 8px #17233b22}
      .recommendation-nav.prev{left:5px}.recommendation-nav.next{right:5px}
      .recommendation-quick-replies{display:flex;width:100%;flex-wrap:wrap;gap:6px;padding:2px 0}
      .recommendation-quick-reply{border-color:#cbd8f3;background:#f4f7ff;color:#3151a4}
      .recommendation-comparison{width:100%;overflow-x:auto;border:1px solid #dfe6f2;border-radius:13px;background:#fff}
      .recommendation-comparison table{width:100%;border-collapse:collapse;font-size:10px}
      .recommendation-comparison th,.recommendation-comparison td{min-width:115px;border-bottom:1px solid #edf0f5;padding:8px;text-align:left;vertical-align:top;color:#40516d}
      .recommendation-comparison th{color:#223454;font-weight:750}
      .recommendation-empty,.recommendation-error,.recommendation-loading{width:100%;border-radius:13px;padding:11px 12px;font-size:11px;line-height:1.5}
      .recommendation-empty{border:1px dashed #cbd5e1;background:#f8fafc;color:#53627a}
      .recommendation-error{border:1px solid #fecaca;background:#fff1f2;color:#a42636}
      .recommendation-loading{border:1px solid #dfe6f2;background:#fff;color:#58667b}
      .recommendation-skeleton{height:9px;margin:8px 0;border-radius:5px;background:linear-gradient(90deg,#edf1f7,#f8faff,#edf1f7);background-size:200% 100%;animation:sp-recommend-shimmer 1.2s infinite}
      @keyframes sp-recommend-shimmer{to{background-position:-200% 0}}
      @media(max-width:600px){.recommendation-track{grid-auto-columns:minmax(225px,84%)}.recommendation-image-wrap{height:145px}.recommendation-nav{display:none}}
      @media(prefers-reduced-motion:reduce){.recommendation-skeleton{animation:none}}
    `;
    shadow.appendChild(style);
  }

  function ProductActionBar(product, index, options, getSelectedVariant = () => product) {
    const actions = document.createElement("div");
    actions.className = "recommendation-actions";
    const url = safeExternalUrl(product.product_url);
    if (url && options.availableActions?.includes("view_product")) {
      const link = document.createElement("a");
      link.className = "recommendation-action primary";
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "View details";
      link.setAttribute("aria-label", `View ${product.title} in the store (opens in a new tab)`);
      link.addEventListener("click", () => options.onProductClick?.(product));
      actions.appendChild(link);
    }
    if (typeof options.onReject === "function") {
      const reject = document.createElement("button");
      reject.className = "recommendation-action";
      reject.type = "button";
      reject.textContent = "Not relevant";
      reject.setAttribute("aria-label", `Mark ${product.title} as not relevant`);
      reject.addEventListener("click", () => { options.onReject(product); reject.disabled = true; reject.textContent = "Feedback sent"; });
      actions.appendChild(reject);
    }
    if (typeof options.onCompare === "function") {
      const compare = document.createElement("button");
      compare.className = "recommendation-action";
      compare.type = "button";
      compare.textContent = options.selectedCompareProductIds?.includes(product.product_id) ? "Remove compare" : "Add to compare";
      compare.setAttribute("aria-label", `${compare.textContent}: ${product.title}`);
      compare.setAttribute("aria-pressed", String(options.selectedCompareProductIds?.includes(product.product_id) || false));
      compare.addEventListener("click", () => {
        const selected = options.onCompare(index, {
          product_id: product.product_id,
          variant_id: getSelectedVariant().variant_id,
        });
        if (typeof selected !== "boolean") return;
        compare.textContent = selected ? "Remove compare" : "Add to compare";
        compare.setAttribute("aria-label", `${compare.textContent}: ${product.title}`);
        compare.setAttribute("aria-pressed", String(selected));
        options.onCompareSelectionChange?.();
      });
      actions.appendChild(compare);
    }
    // Cart is intentionally offered only when the server explicitly advertises
    // a supported action. This API currently has no price-recheck/cart endpoint.
    if (Array.isArray(product.available_actions) && product.available_actions.includes("add_to_cart")) {
      const cart = document.createElement("button");
      cart.className = "recommendation-action";
      cart.type = "button";
      cart.textContent = "Add to cart";
      cart.disabled = typeof options.onAddToCart !== "function";
      cart.addEventListener("click", () => options.onAddToCart?.(getSelectedVariant().variant_id));
      actions.appendChild(cart);
    }
    return actions;
  }

  function ProductRecommendationCard(product, index, options) {
    const card = document.createElement("article");
    card.className = "recommendation-card";
    card.setAttribute("aria-label", `Recommendation ${index + 1}: ${product.title}`);
    const imageWrap = document.createElement("div");
    imageWrap.className = "recommendation-image-wrap";
    const imageUrl = safeExternalUrl(product.image_url);
    if (imageUrl) {
      const image = document.createElement("img");
      image.className = "recommendation-image";
      image.src = imageUrl;
      image.alt = product.title;
      image.loading = "lazy";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => {
        image.remove();
        imageWrap.textContent = "Image unavailable";
      }, { once: true });
      imageWrap.appendChild(image);
    } else {
      imageWrap.textContent = "No product image";
    }
    const body = document.createElement("div");
    body.className = "recommendation-body";
    body.appendChild(textElement("h3", "recommendation-title", product.title));
    const variantOptions = Array.isArray(product.variant_options) && product.variant_options.length
      ? product.variant_options
      : [{
          variant_id: product.variant_id,
          variant_title: product.variant_title,
          price: product.price,
          currency: product.currency,
          availability: product.availability,
          verified_attributes: product.verified_attributes || {},
        }];
    let selectedVariant = variantOptions.find((variant) => variant.variant_id === product.variant_id) || variantOptions[0];
    if (variantOptions.length > 1) {
      const variantLabel = textElement("label", "recommendation-variant-label", `Choose an option for ${product.title}`);
      const select = document.createElement("select");
      select.className = "recommendation-variant-select";
      select.setAttribute("aria-label", `Variant for ${product.title}`);
      for (const variant of variantOptions) {
        const option = document.createElement("option");
        option.value = variant.variant_id;
        option.textContent = `${variant.variant_title || "Option"} · ${priceLabel(variant.price, variant.currency)}`;
        select.appendChild(option);
      }
      select.value = selectedVariant.variant_id;
      variantLabel.appendChild(select);
      body.appendChild(variantLabel);
    }
    const variantName = textElement("p", "recommendation-limitation recommendation-variant-name", "");
    const price = textElement("div", "recommendation-price", "");
    const availability = selectedVariant.availability || "unknown";
    const status = textElement("span", `recommendation-status ${availability}`, "");
    const reason = textElement("p", "recommendation-reason", "");
    const variantLimitation = textElement("p", "recommendation-limitation", "");
    const list = document.createElement("ul");
    list.className = "recommendation-attrs";
    const renderVariant = (variant) => {
      selectedVariant = variant;
      const title = String(variant.variant_title || "");
      variantName.textContent = title && !["default", "default title"].includes(title.toLowerCase()) ? `Variant: ${title}` : "";
      price.textContent = priceLabel(variant.price, variant.currency);
      const currentAvailability = variant.availability || "unknown";
      status.className = `recommendation-status ${currentAvailability}`;
      status.textContent = currentAvailability === "available" ? "Available in catalog" : currentAvailability === "unavailable" ? "Unavailable" : "Availability not confirmed";
      reason.textContent = variant.reasons?.[0] || product.reasons?.[0] || "";
      variantLimitation.textContent = variant.limitations?.[0] || product.limitations?.[0] || "";
      list.replaceChildren();
      for (const [key, value] of Object.entries(variant.verified_attributes || {}).slice(0, 4)) {
        list.appendChild(textElement("li", "", `${key}: ${value}`));
      }
    };
    const select = body.querySelector("select");
    select?.addEventListener("change", () => {
      const variant = variantOptions.find((option) => option.variant_id === select.value);
      if (variant) {
        renderVariant(variant);
        options.onVariantSelected?.(index, { product_id: product.product_id, variant_id: variant.variant_id });
      }
    });
    renderVariant(selectedVariant);
    body.append(variantName, price, status, reason, list);
    body.appendChild(variantLimitation);
    body.appendChild(ProductActionBar(product, index, options, () => selectedVariant));
    card.append(imageWrap, body);
    return card;
  }

  function ProductRecommendationCarousel(products, options) {
    const carousel = document.createElement("div");
    carousel.className = "recommendation-carousel";
    carousel.setAttribute("role", "region");
    carousel.setAttribute("aria-label", "Recommended products");
    const track = document.createElement("div");
    track.className = "recommendation-track";
    track.tabIndex = 0;
    track.setAttribute("aria-label", "Product recommendations. Use the left and right arrow keys to browse.");
    products.forEach((product, index) => track.appendChild(ProductRecommendationCard(product, index, options)));
    track.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        track.scrollBy({ left: (event.key === "ArrowRight" ? 1 : -1) * track.clientWidth * 0.75, behavior: "smooth" });
      }
    });
    const previous = textElement("button", "recommendation-nav prev", "‹");
    previous.type = "button";
    previous.setAttribute("aria-label", "Previous recommended products");
    previous.addEventListener("click", () => track.scrollBy({ left: -track.clientWidth * 0.75, behavior: "smooth" }));
    const next = textElement("button", "recommendation-nav next", "›");
    next.type = "button";
    next.setAttribute("aria-label", "Next recommended products");
    next.addEventListener("click", () => track.scrollBy({ left: track.clientWidth * 0.75, behavior: "smooth" }));
    carousel.append(previous, track, next);
    return carousel;
  }

  function ProductComparisonView(payload) {
    const wrap = document.createElement("div");
    wrap.className = "recommendation-comparison";
    const table = document.createElement("table");
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    headRow.appendChild(textElement("th", "", "Verified details"));
    (payload.products || []).forEach((product) => headRow.appendChild(textElement("th", "", product.title)));
    head.appendChild(headRow);
    const body = document.createElement("tbody");
    const rows = [
      ["Price", ...(payload.products || []).map((p) => priceLabel(p.price, p.currency))],
      ["Availability", ...(payload.products || []).map((p) => p.availability || "unknown")],
      ["Brand", ...(payload.products || []).map((p) => p.brand || "Not listed")],
      ...[...new Set((payload.products || []).flatMap((p) => Object.keys(p.verified_attributes || {})))].map((key) => [key, ...(payload.products || []).map((p) => p.normalized_attributes?.[key] || p.verified_attributes?.[key] || "Not listed")]),
    ];
    for (const values of rows) {
      const tr = document.createElement("tr");
      values.forEach((value, index) => tr.appendChild(textElement(index === 0 ? "th" : "td", "", value)));
      body.appendChild(tr);
    }
    table.append(head, body);
    wrap.appendChild(table);
    if (payload.differences?.length) wrap.appendChild(textElement("p", "recommendation-limitation", payload.differences.join(" · ")));
    if (payload.trade_offs?.length) {
      const tradeoffs = document.createElement("ul");
      tradeoffs.className = "recommendation-limitation";
      tradeoffs.setAttribute("aria-label", "Trade-offs based on your priorities");
      for (const tradeoff of payload.trade_offs.slice(0, 8)) tradeoffs.appendChild(textElement("li", "", tradeoff));
      wrap.appendChild(tradeoffs);
    }
    return wrap;
  }

  function RecommendationQuickReplies(replies, onSelect) {
    const row = document.createElement("div");
    row.className = "recommendation-quick-replies";
    for (const reply of (replies || []).slice(0, 4)) {
      const button = textElement("button", "recommendation-quick-reply", reply);
      button.type = "button";
      button.addEventListener("click", () => onSelect?.(reply));
      row.appendChild(button);
    }
    return row;
  }

  function RecommendationLoadingState() {
    const loading = textElement("div", "recommendation-loading", "Finding products that match your preferences…");
    loading.setAttribute("role", "status");
    loading.appendChild(textElement("div", "recommendation-skeleton", ""));
    loading.appendChild(textElement("div", "recommendation-skeleton", ""));
    return loading;
  }

  function RecommendationEmptyState(message) {
    const empty = textElement("div", "recommendation-empty", message || "I couldn’t find products that match those preferences. You can adjust a filter and try again.");
    empty.setAttribute("role", "status");
    return empty;
  }

  function RecommendationErrorState(message, onRetry) {
    const error = textElement("div", "recommendation-error", message || "Recommendations are temporarily unavailable. Please try again.");
    error.setAttribute("role", "alert");
    if (onRetry) {
      const retry = textElement("button", "recommendation-action", "Try again");
      retry.type = "button";
      retry.addEventListener("click", onRetry);
      error.appendChild(retry);
    }
    return error;
  }

  function ProductRecommendationMessage(payload, options = {}) {
    const section = document.createElement("section");
    section.className = "recommendation-message";
    section.setAttribute("aria-label", "Product recommendation response");
    section.appendChild(textElement("div", "recommendation-intro", payload.explanation || "Here are some products from the store catalog."));
    if (payload.response_type === "comparison") {
      if (payload.products?.length) {
        section.appendChild(ProductComparisonView(payload));
        options.onComparison?.();
      }
      else section.appendChild(RecommendationEmptyState(payload.explanation));
    } else if (payload.response_type === "recommendations" && payload.products?.length) {
      const canCompare = typeof options.onCompare === "function";
      const compareSelected = textElement("button", "recommendation-action recommendation-compare-submit", "Select 2–4 products to compare");
      compareSelected.type = "button";
      compareSelected.disabled = (options.getCompareCount?.() || 0) < 2;
      compareSelected.addEventListener("click", () => options.onCompareSelected?.());
      section.appendChild(ProductRecommendationCarousel(payload.products, {
        availableActions: payload.available_actions || [],
        selectedCompareProductIds: options.selectedCompareProductIds || [],
        onCompare: canCompare ? (index, selection) => options.onCompare(index, selection) : undefined,
        onVariantSelected: options.onVariantSelected,
        onCompareSelectionChange: () => {
          const count = options.getCompareCount?.() || 0;
          compareSelected.disabled = count < 2;
          compareSelected.textContent = count ? `Compare selected (${count})` : "Select 2–4 products to compare";
        },
        onAddToCart: options.onAddToCart,
        onProductClick: options.onProductClick,
        onReject: options.onReject,
      }));
      if (typeof options.onImpression === "function" && "IntersectionObserver" in window) {
        const cards = section.querySelectorAll(".recommendation-card");
        const seen = new WeakSet();
        const observer = new IntersectionObserver((entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting || seen.has(entry.target)) continue;
            seen.add(entry.target);
            const index = [...cards].indexOf(entry.target);
            if (index >= 0) options.onImpression(payload.products[index]);
            observer.unobserve(entry.target);
          }
        }, { threshold: 0.35 });
        cards.forEach((card) => observer.observe(card));
      }
      if (canCompare) section.appendChild(compareSelected);
    } else {
      section.appendChild(RecommendationEmptyState(payload.explanation));
    }
    if (payload.limitations?.length) section.appendChild(textElement("p", "recommendation-limitation", payload.limitations.join(" ")));
    if (payload.suggested_follow_ups?.length) {
      section.appendChild(RecommendationQuickReplies(payload.suggested_follow_ups, options.onQuickReply));
    }
    return section;
  }

  window.SupportPilotRecommendationUI = {
    mountStyles,
    ProductRecommendationMessage,
    ProductRecommendationCard,
    ProductRecommendationCarousel,
    ProductComparisonView,
    ProductActionBar,
    RecommendationQuickReplies,
    RecommendationLoadingState,
    RecommendationEmptyState,
    RecommendationErrorState,
  };
})();
