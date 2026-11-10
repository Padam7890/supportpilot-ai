(() => {
  const script = document.currentScript;
  const publicId = script?.getAttribute("data-widget-id");
  if (!publicId) {
    console.error("[SupportPilot widget] Missing data-widget-id; chat launcher was not mounted.");
    return;
  }

  if (document.getElementById("supportpilot-widget-host")) return;

  let apiBase = (script.getAttribute("data-api-base") || new URL("/api", script.src).href).replace(/\/$/, "");
  if (apiBase.endsWith("/api/widget")) apiBase = apiBase.slice(0, -"/widget".length);

  const sessionKey = `supportpilot-widget-session:${publicId}`;
  const pendingKey = `supportpilot-widget-pending:${publicId}`;
  const host = document.createElement("div");
  host.id = "supportpilot-widget-host";
  host.style.cssText = "all:initial!important;position:fixed!important;right:20px!important;bottom:20px!important;z-index:2147483000!important;display:block!important;visibility:visible!important;opacity:1!important;pointer-events:auto!important";
  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `
    <style>
      :host{all:initial;color:#17233b;font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
      *,*::before,*::after{box-sizing:border-box}
      button,input,textarea{font:inherit}
      button{cursor:pointer}
      .shell{display:flex;flex-direction:column;align-items:flex-end;gap:12px}
      .launcher{display:flex;align-items:center;gap:10px;border:0;border-radius:999px;background:linear-gradient(135deg,#2355e9,#483de0);color:#fff;padding:13px 17px 13px 13px;box-shadow:0 12px 34px #1d3b8c52;font-weight:700;transition:transform .18s,box-shadow .18s}
      .launcher[hidden]{display:none}
      .launcher:hover{transform:translateY(-2px);box-shadow:0 16px 40px #1d3b8c60}
      .launcher:focus-visible,.close:focus-visible,.quick:focus-visible,.send:focus-visible,.card-button:focus-visible{outline:3px solid #f6c945;outline-offset:3px}
      .launcher-icon{display:grid;place-items:center;width:31px;height:31px;border-radius:50%;background:#ffffff26}
      .panel{display:none;flex-direction:column;width:min(390px,calc(100vw - 28px));height:min(640px,calc(100dvh - 96px));min-height:390px;overflow:hidden;border:1px solid #dfe5f1;border-radius:24px;background:#f8faff;box-shadow:0 24px 74px #15264a38;transform-origin:bottom right;animation:pop .2s ease-out}
      .panel.open{display:flex}
      @keyframes pop{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}
      @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}
      .head{display:flex;align-items:center;gap:11px;padding:15px 16px;background:linear-gradient(120deg,#234fdf,#483ddf);color:#fff}
      .brand-mark{display:grid;place-items:center;flex:0 0 38px;width:38px;height:38px;border:1px solid #ffffff47;border-radius:13px;background:#ffffff20;font-size:17px;font-weight:800}
      .brand-copy{min-width:0;flex:1}
      .store-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px;font-weight:750}
      .assistant-name{display:block;color:#e1e8ff;font-size:11px;font-weight:500}
      .availability{display:inline-flex;align-items:center;gap:5px;margin-top:2px;color:#dce7ff;font-size:10px}
      .dot{width:7px;height:7px;border-radius:50%;background:#5ef0b0;box-shadow:0 0 0 3px #5ef0b020}
      .close{display:grid;place-items:center;width:34px;height:34px;border:0;border-radius:11px;background:#ffffff1f;color:#fff;font-size:22px;line-height:1}
      .close:hover{background:#ffffff32}
      .thread{display:flex;flex:1;flex-direction:column;gap:10px;overflow:auto;padding:16px 13px 12px;scroll-behavior:smooth}
      .welcome{padding:3px 3px 8px}
      .welcome h2{margin:0;color:#182442;font-size:18px;letter-spacing:-.02em}
      .welcome p{margin:5px 0 13px;color:#687691;font-size:12px;line-height:1.55}
      .quick-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}
      .quick{display:flex;align-items:center;gap:7px;min-height:38px;border:1px solid #dce4f2;border-radius:12px;background:#fff;padding:8px 9px;color:#30415f;text-align:left;font-size:11px;font-weight:650;box-shadow:0 2px 5px #15264a08;transition:border-color .15s,background .15s}
      .quick:hover{border-color:#9eb6f5;background:#f2f6ff}
      .quick-icon{color:#4267d9;font-size:14px}
      .message-row{display:flex;flex-direction:column;max-width:88%;gap:3px;animation:rise .18s ease-out}
      .message-row.streaming-row{animation:none}
      .message-row.customer{align-self:flex-end;align-items:flex-end}
      .message-row.assistant,.message-row.agent{align-self:flex-start;align-items:flex-start}
      @keyframes rise{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
      .message{white-space:pre-wrap;overflow-wrap:anywhere;border-radius:17px;padding:10px 12px;font-size:12px;line-height:1.55}
      .message p,.message ul,.message ol{margin:0}
      .message p+p,.message p+ul,.message p+ol,.message ul+p,.message ol+p,.message ul+ol,.message ol+ul{margin-top:12px}
      .message ul,.message ol{padding-left:19px}
      .message li+li{margin-top:3px}
      .customer .message{border-bottom-right-radius:5px;background:#3158d8;color:#fff}
      .assistant .message{border:1px solid #e2e8f2;border-bottom-left-radius:5px;background:#fff;color:#25334d;box-shadow:0 2px 8px #19294a0a}
      .agent .message{border-bottom-left-radius:5px;background:#e6edff;color:#263a67}
      .message-meta{display:flex;align-items:center;gap:7px;padding:0 3px;color:#8a96aa;font-size:9px}
      .typing{display:flex;align-items:center;gap:4px;width:max-content;border:1px solid #e2e8f2;border-radius:14px;background:#fff;padding:11px 13px}
      .typing span{width:5px;height:5px;border-radius:50%;background:#8492ad;animation:bounce 1s infinite ease-in-out}
      .typing span:nth-child(2){animation-delay:.12s}.typing span:nth-child(3){animation-delay:.24s}
      @keyframes bounce{0%,60%,100%{transform:translateY(0);opacity:.45}30%{transform:translateY(-3px);opacity:1}}
      .context-card{width:100%;border:1px solid #d8e2f5;border-radius:15px;background:#fff;padding:12px;box-shadow:0 5px 18px #182b530c}
      .context-card h3{margin:0;color:#223454;font-size:12px;font-weight:750}
      .context-card p{margin:5px 0 9px;color:#687691;font-size:10px;line-height:1.5}
      .context-card input{display:block;width:100%;min-height:38px;margin-top:7px;border:1px solid #d7dfeb;border-radius:10px;background:#fff;padding:8px 10px;color:#202d45;font-size:12px;outline:none}
      .context-card input:focus{border-color:#6f91ee;box-shadow:0 0 0 3px #4267d922}
      .consent{display:flex;align-items:flex-start;gap:7px;margin:9px 0;color:#687691;font-size:10px;line-height:1.4}
      .consent input{flex:0 0 14px;width:14px;height:14px;min-height:0;margin:0;accent-color:#3158d8}
      .card-button{width:100%;min-height:37px;margin-top:8px;border:0;border-radius:10px;background:#3158d8;color:#fff;font-size:11px;font-weight:700}
      .card-button.secondary{border:1px solid #dce4f2;background:#fff;color:#344563}
      .card-button:hover{filter:brightness(.97)}.card-button:disabled{cursor:wait;opacity:.55}
      .card-error{margin:7px 1px 0!important;color:#b42336!important;font-size:10px!important}
      .form{display:flex;align-items:flex-end;gap:8px;border-top:1px solid #e8edf5;background:#fff;padding:11px 12px 10px}
      .compose{flex:1;min-height:42px;max-height:115px;resize:none;border:1px solid #dbe3ef;border-radius:14px;background:#f9fbff;padding:10px 12px;color:#1f2c44;font-size:12px;line-height:1.4;outline:none}
      .compose:focus{border-color:#7c99e9;box-shadow:0 0 0 3px #4267d918}
      .compose::placeholder{color:#99a4b7}
      .send{display:grid;place-items:center;flex:0 0 42px;width:42px;height:42px;border:0;border-radius:13px;background:#3158d8;color:#fff}
      .send:hover{background:#2549c2}.send:disabled{cursor:wait;opacity:.45}
      .foot{display:flex;justify-content:space-between;align-items:center;gap:8px;background:#fff;padding:0 14px 10px;color:#8b96a8;font-size:9px}
      .status{min-height:14px;padding:0 13px 5px;background:#fff;color:#64728b;font-size:10px}
      .status.error{color:#b42336}
      .card-status{min-height:12px;margin-top:7px;color:#64728b;font-size:10px}
      @media(max-width:600px){
        :host{right:10px!important;bottom:10px!important}
        .panel{position:fixed;right:0;bottom:0;width:100vw;height:100dvh;max-height:100dvh;min-height:0;border-radius:20px 20px 0 0;border-bottom:0}
        .shell{gap:0}.launcher{position:fixed;right:12px;bottom:12px}
        .thread{padding:18px 14px 14px}.head{padding-top:max(15px,env(safe-area-inset-top))}
        .form{padding-bottom:max(10px,env(safe-area-inset-bottom))}
      }
    </style>
    <div class="shell">
      <section class="panel" id="supportpilot-chat-panel" role="dialog" aria-label="Customer support chat" aria-modal="false" aria-hidden="true">
        <header class="head">
          <span class="brand-mark" aria-hidden="true">S</span>
          <div class="brand-copy"><div class="store-name">Support</div><span class="assistant-name">AI support assistant</span><span class="availability"><i class="dot" aria-hidden="true"></i><span class="availability-text">Chat available</span></span></div>
          <button class="close" type="button" aria-label="Close support chat">×</button>
        </header>
        <div class="thread" aria-live="polite" aria-relevant="additions text"></div>
        <div class="status" role="status" aria-live="polite"></div>
        <form class="form">
          <textarea class="compose" name="content" aria-label="Message the support assistant" placeholder="Ask us anything…" rows="1" maxlength="4000" required></textarea>
          <button class="send" type="submit" aria-label="Send message" disabled><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12 20 4l-4.5 16-3.2-6.3L4 12Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m12.3 13.7 4.2-4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
        </form>
        <div class="foot"><span>Powered by SupportPilot AI</span><span>Replies may be reviewed by the store team</span></div>
      </section>
      <button class="launcher" type="button" aria-expanded="false" aria-controls="supportpilot-chat-panel">
        <span class="launcher-icon" aria-hidden="true"><svg width="19" height="19" viewBox="0 0 24 24" fill="none"><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H6l-3 2v-5.5A7.5 7.5 0 1 1 20 11.5Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M8 11.5h.01M12.5 11.5h.01M17 11.5h.01" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg></span>
        <span>Chat with us</span>
      </button>
    </div>`;
  (document.body || document.documentElement).appendChild(host);

  const panel = shadow.querySelector(".panel");
  const launcher = shadow.querySelector(".launcher");
  const thread = shadow.querySelector(".thread");
  const form = shadow.querySelector(".form");
  const compose = shadow.querySelector(".compose");
  const sendButton = shadow.querySelector(".send");
  const status = shadow.querySelector(".status");
  let config;
  let session;
  const ACTIVE_HISTORY_REFRESH_MS = 5_000;
  const FINAL_HISTORY_REFRESH_MS = 500;
  const STREAM_WORD_INTERVAL_MS = 30;
  const STREAM_MAX_WORDS_PER_FRAME = 2;
  const IDLE_HISTORY_REFRESH_MS = 30_000;
  const MAX_HISTORY_RETRY_MS = 120_000;
  let historyTimer;
  let historyPollController;
  let historyPollFailures = 0;
  let firstAttempt;
  let followingAttempt;
  let pending = false;
  let waitingForAssistant = false;
  let assistantWaitStartedAt = 0;
  let conversationMode = "human";
  let verifiedOrder = false;
  let latestMessages = [];
  let lastHistorySignature = "";
  let recommendationUIPromise;
  let compareSelections = [];
  let lastRecommendationMessageId = null;
  let nextRecommendationSelections = null;

  function loadRecommendationUI() {
    if (window.SupportPilotRecommendationUI) {
      window.SupportPilotRecommendationUI.mountStyles(shadow);
      return Promise.resolve(window.SupportPilotRecommendationUI);
    }
    if (recommendationUIPromise) return recommendationUIPromise;
    recommendationUIPromise = new Promise((resolve, reject) => {
      const recommendationScript = document.createElement("script");
      const recommendationUrl = new URL("supportpilot-recommendations.js", script.src);
      recommendationUrl.searchParams.set("v", new URL(script.src).searchParams.get("v") || "1");
      recommendationScript.src = recommendationUrl.href;
      recommendationScript.async = true;
      recommendationScript.onload = () => {
        const ui = window.SupportPilotRecommendationUI;
        if (!ui) return reject(new Error("Product recommendations could not be loaded."));
        ui.mountStyles(shadow);
        resolve(ui);
      };
      recommendationScript.onerror = () => reject(new Error("Product recommendations could not be loaded."));
      document.head.appendChild(recommendationScript);
    });
    return recommendationUIPromise;
  }

  function compareProductsAt(index, selection) {
    const existing = compareSelections.findIndex((item) => item.selection.product_id === selection.product_id);
    if (existing >= 0) {
      compareSelections.splice(existing, 1);
      setStatus(`Removed product ${index + 1}. ${compareSelections.length} selected for comparison.`);
      return false;
    }
    if (compareSelections.length >= 4) {
      setStatus("Compare up to four products at a time.", true);
      return false;
    }
    compareSelections.push({ index, selection });
    setStatus(`${compareSelections.length} product${compareSelections.length === 1 ? "" : "s"} selected. Choose 2–4, then compare.`);
    return true;
  }

  function updateComparedVariant(_index, selection) {
    const existing = compareSelections.find((item) => item.selection.product_id === selection.product_id);
    if (existing) existing.selection = selection;
  }

  function compareSelectedProducts() {
    if (compareSelections.length < 2 || compareSelections.length > 4) {
      setStatus("Select between two and four different products to compare.", true);
      return;
    }
    const ordered = [...compareSelections].sort((left, right) => left.index - right.index);
    const names = ["first", "second", "third", "fourth"];
    compose.value = `Compare the ${ordered.map((item) => names[item.index] || `${item.index + 1}`).join(", ")} products`;
    nextRecommendationSelections = ordered.map((item) => item.selection);
    resizeComposer();
    sendMessage();
  }

  function setStatus(message, error = false) {
    status.textContent = message;
    status.classList.toggle("error", error);
  }

  function safeError(body, fallback) {
    return body?.detail || body?.message || fallback;
  }

  function timestamp(value) {
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
  }

  function appendReplyText(node, text, partial) {
    const parts = text.split(/(\*\*[^*\n]+\*\*)/g);
    for (let index = 0; index < parts.length; index++) {
      const part = parts[index];
      if (index % 2 === 1) {
        const strong = document.createElement("strong");
        strong.textContent = part.slice(2, -2);
        node.append(strong);
      } else {
        node.append(partial && index === parts.length - 1 ? part.replace(/\*\*([^*]*)\*?$/, "$1").replace(/\*$/, "") : part);
      }
    }
  }

  function normalizeAssistantLineBreaks(content) {
    // Model output and previously stored messages may contain one or two
    // layers of escaped newline separators. Never interpret HTML here.
    return String(content || "").replace(/\\\\\\\\n/g, "\\n").replace(/\\\\n/g, "\\n").replace(/\\r\\n/g, "\\n");
  }

  function renderAssistantMessage(bubble, content, partial = false) {
    const fragment = document.createDocumentFragment();
    let block = null;
    let blockType = "";
    for (const line of content.split(/\r?\n/)) {
      if (!line.trim()) {
        block = null;
        continue;
      }
      const item = line.match(/^\s*(?:([-*+])|(\d+)[.)])\s+(.+)$/);
      if (item) {
        const type = item[1] ? "ul" : "ol";
        if (!block || blockType !== type) {
          block = document.createElement(type);
          if (type === "ol") block.start = Number(item[2]);
          blockType = type;
          fragment.append(block);
        }
        const li = document.createElement("li");
        appendReplyText(li, item[3], partial);
        block.append(li);
      } else {
        if (!block || blockType !== "p") {
          block = document.createElement("p");
          blockType = "p";
          fragment.append(block);
        } else {
          block.append("\n");
        }
        appendReplyText(block, line.replace(/^#{1,6}\s+(.+)$/, "**$1**"), partial);
      }
    }
    bubble.replaceChildren(fragment);
  }

  function addMessage(message, { canCompare = false } = {}) {
    const sender = message.sender_type === "customer" ? "customer" : message.sender_type === "agent" ? "agent" : "assistant";
    const row = document.createElement("article");
    row.className = `message-row ${sender}`;
    row.setAttribute("aria-label", `${sender === "customer" ? "You" : sender === "agent" ? "Support teammate" : config?.assistant_name || "AI assistant"}, ${timestamp(message.created_at)}`);
    const bubble = document.createElement("div");
    bubble.className = "message";
    if (sender === "assistant") renderAssistantMessage(bubble, message.content);
    else bubble.textContent = message.content;
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("span");
    name.textContent = sender === "customer" ? "You" : sender === "agent" ? (message.sender_name || "Support teammate") : (config?.assistant_name || "AI assistant");
    const time = document.createElement("time");
    time.textContent = timestamp(message.created_at);
    meta.append(name, time);
    if (!message.recommendation) row.appendChild(bubble);
    if (message.recommendation && window.SupportPilotRecommendationUI) {
      const recommendation = window.SupportPilotRecommendationUI.ProductRecommendationMessage(message.recommendation, {
        onImpression: (product) => trackRecommendationEvent(message.id, "impression", product),
        onProductClick: (product) => trackRecommendationEvent(message.id, "product_click", product),
        onReject: (product) => trackRecommendationEvent(message.id, "rejection", product),
        onComparison: () => trackRecommendationEvent(message.id, "comparison"),
        onCompare: canCompare ? compareProductsAt : undefined,
        onVariantSelected: canCompare ? updateComparedVariant : undefined,
        selectedCompareProductIds: compareSelections.map((item) => item.selection.product_id),
        getCompareCount: () => compareSelections.length,
        onCompareSelected: compareSelectedProducts,
        onQuickReply: (reply) => {
          compose.value = reply;
          resizeComposer();
          sendMessage();
        },
      });
      row.appendChild(recommendation);
      row.classList.add("recommendation-message");
    }
    row.appendChild(meta);
    thread.appendChild(row);
    return row;
  }

  function addWelcome() {
    const welcome = document.createElement("section");
    welcome.className = "welcome";
    const title = document.createElement("h2");
    title.textContent = config?.welcome_message || `Hi! Welcome to ${config?.store_name || "our store"}.`;
    const intro = document.createElement("p");
    intro.textContent = "I can help with product questions, store policies, and order updates. What can I help you with?";
    const actions = document.createElement("div");
    actions.className = "quick-actions";
    actions.setAttribute("aria-label", "Suggested questions");
    const items = [
      ["↗", "Track an order", "I’d like to track an order."],
      ["↶", "Cancel an order", "I’d like to request an order cancellation."],
      ["?", "Returns & refunds", "What is your return and refund policy?"],
      ["✦", "Product question", "I have a question about a product."],
    ];
    for (const [iconText, label, message] of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "quick";
      const icon = document.createElement("span");
      icon.className = "quick-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = iconText;
      const text = document.createElement("span");
      text.textContent = label;
      button.append(icon, text);
      button.addEventListener("click", () => {
        compose.value = message;
        sendMessage();
      });
      actions.appendChild(button);
    }
    welcome.append(title, intro, actions);
    thread.appendChild(welcome);
  }

  function addTyping() {
    const row = document.createElement("div");
    row.className = "message-row assistant typing-row";
    row.setAttribute("role", "status");
    row.setAttribute("aria-label", `${config?.assistant_name || "AI assistant"} is typing`);
    const dots = document.createElement("div");
    dots.className = "typing";
    dots.innerHTML = "<span></span><span></span><span></span>";
    row.appendChild(dots);
    thread.appendChild(row);
  }

  function containsOrderIntent(messages) {
    const latestCustomer = [...messages].reverse().find((item) => item.sender_type === "customer")?.content || "";
    return /\b(order|track|tracking|shipment|shipped)\b/i.test(latestCustomer);
  }

  function containsCancellationIntent(messages) {
    const latestCustomer = [...messages].reverse().find((item) => item.sender_type === "customer")?.content || "";
    const latest = messages.at(-1);
    if (latest?.sender_type === "assistant") {
      return /\b(?:submit a cancellation request|use the cancellation request card)\b/i.test(latest.content || "");
    }
    return /\b(?:cancel|cancellation)\b.*\b(?:order|purchase)\b/i.test(latestCustomer);
  }

  function cancellationWasSubmitted(messages) {
    // A confirmation from an earlier turn must not hide the verification flow
    // when the shopper starts a new cancellation request later in the chat.
    const lastCustomerIndex = messages.reduce((result, item, index) => item.sender_type === "customer" ? index : result, -1);
    if (lastCustomerIndex < 0) return false;
    return messages.slice(lastCustomerIndex + 1).some((item) =>
      item.sender_type === "assistant" && /(?:i sent your cancellation request to the support team|your cancellation request is with the support team)/i.test(item.content || "")
    );
  }

  function latestAssistantRequestsVerification(messages) {
    const lastCustomerIndex = messages.reduce((result, item, index) => item.sender_type === "customer" ? index : result, -1);
    if (lastCustomerIndex < 0) return false;
    const latestAssistant = [...messages.slice(lastCustomerIndex + 1)].reverse().find((item) => item.sender_type === "assistant");
    return Boolean(latestAssistant && /verification card|verify (?:the|your )?order|one-time code|secure card below/i.test(latestAssistant.content || ""));
  }

  function addOrderVerificationCard() {
    const card = document.createElement("section");
    card.className = "context-card";
    card.setAttribute("aria-label", "Verify an order");
    const title = document.createElement("h3");
    title.textContent = "Verify your order";
    const description = document.createElement("p");
    description.textContent = "Enter the order number and checkout email. We’ll send a one-time code to the email attached to the order before showing details.";
    const order = document.createElement("input");
    order.name = "order_number";
    order.autocomplete = "off";
    order.maxLength = 60;
    order.placeholder = "Order number, e.g. #1001";
    order.setAttribute("aria-label", "Shopify order number");
    const email = document.createElement("input");
    email.name = "email";
    email.type = "email";
    email.autocomplete = "email";
    email.maxLength = 254;
    email.placeholder = "Email used at checkout";
    email.setAttribute("aria-label", "Email used at checkout");
    const consentLabel = document.createElement("label");
    consentLabel.className = "consent";
    const consent = document.createElement("input");
    consent.type = "checkbox";
    consent.setAttribute("aria-label", "Consent to email verification");
    const consentText = document.createElement("span");
    consentText.textContent = "I agree to use this email to verify this order and receive a one-time code.";
    consentLabel.append(consent, consentText);
    const request = document.createElement("button");
    request.type = "button";
    request.className = "card-button";
    request.textContent = "Email verification code";
    const message = document.createElement("div");
    message.className = "card-status";
    message.setAttribute("role", "status");

    request.addEventListener("click", async () => {
      if (!session) return showCardError(message, "Send a message first to start a secure chat.");
      if (!order.value.trim() || !email.value.trim()) return showCardError(message, "Enter both the order number and checkout email.");
      if (!consent.checked) return showCardError(message, "Consent is required to send a verification code.");
      request.disabled = true;
      message.textContent = "Checking the order and sending a code…";
      message.classList.remove("card-error");
      try {
        const result = await callVisitorApi(`/widget/conversations/${encodeURIComponent(session.conversation_id)}/order-verification`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ order_number: order.value.trim(), email: email.value.trim(), consent: true }),
        });
        message.textContent = result.message;
        addCodeEntry(card, { order, email, message, cancellation: containsCancellationIntent(latestMessages) });
      } catch (error) {
        showCardError(message, error.message || "Could not request a verification code.");
      } finally {
        request.disabled = false;
      }
    });
    card.append(title, description, order, email, consentLabel, request, message);
    thread.appendChild(card);
    card.scrollIntoView({ block: "nearest" });
    order.focus({ preventScroll: true });
  }

  function addCodeEntry(card, values) {
    if (card.querySelector(".code-entry")) return;
    const wrapper = document.createElement("div");
    wrapper.className = "code-entry";
    const code = document.createElement("input");
    code.inputMode = "numeric";
    code.autocomplete = "one-time-code";
    code.maxLength = 6;
    code.placeholder = "6-digit code";
    code.setAttribute("aria-label", "Email verification code");
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "card-button secondary";
    confirm.textContent = "Verify and check order";
    confirm.addEventListener("click", async () => {
      if (!/^\d{6}$/.test(code.value.trim())) return showCardError(values.message, "Enter the 6-digit code from your email.");
      confirm.disabled = true;
      values.message.textContent = "Verifying and checking Shopify…";
      try {
        const result = await callVisitorApi(`/widget/conversations/${encodeURIComponent(session.conversation_id)}/order-verification/confirm`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ code: code.value.trim() }),
        });
        verifiedOrder = true;
        values.message.textContent = result.message;
        code.disabled = true;
        confirm.remove();
        if (result.tracking?.length) {
          const list = document.createElement("ul");
          list.style.cssText = "margin:8px 0 0;padding-left:17px;color:#30415f;font-size:10px";
          for (const tracking of result.tracking) {
            const line = document.createElement("li");
            const link = document.createElement("a");
            if (tracking.url && /^https:\/\//i.test(tracking.url)) {
              link.href = tracking.url;
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              link.textContent = [tracking.company, tracking.number].filter(Boolean).join(" · ") || "Track shipment";
            } else {
              link.textContent = [tracking.company, tracking.number].filter(Boolean).join(" · ") || "Tracking information";
            }
            line.appendChild(link);
            list.appendChild(line);
          }
          card.appendChild(list);
        }
        if (values.cancellation) addCancellationCard(values.order.value.trim(), card);
        if (result.order_number) await loadHistory();
      } catch (error) {
        showCardError(values.message, error.message || "Could not verify this code.");
      } finally {
        confirm.disabled = false;
      }
    });
    wrapper.append(code, confirm);
    card.appendChild(wrapper);
    code.focus({ preventScroll: true });
  }

  function addCancellationCard(orderNumber, after) {
    if (thread.querySelector(".cancel-card")) return;
    const card = document.createElement("section");
    card.className = "context-card cancel-card";
    card.setAttribute("aria-label", "Request order cancellation");
    const title = document.createElement("h3");
    title.textContent = `Request cancellation for ${orderNumber}`;
    const description = document.createElement("p");
    description.textContent = "This sends a request to the store team. Nothing changes until an authorized teammate approves it.";
    const reason = document.createElement("input");
    reason.maxLength = 500;
    reason.placeholder = "Reason for cancellation";
    reason.setAttribute("aria-label", "Reason for cancellation");
    const submit = document.createElement("button");
    submit.type = "button";
    submit.className = "card-button";
    submit.textContent = "Send cancellation request";
    const message = document.createElement("div");
    message.className = "card-status";
    message.setAttribute("role", "status");
    let attempt;
    submit.addEventListener("click", async () => {
      const cleanReason = reason.value.trim();
      if (cleanReason.length < 5) return showCardError(message, "Add a short reason so the team can review your request.");
      attempt ??= { reason: cleanReason, key: crypto.randomUUID() };
      if (attempt.reason !== cleanReason) attempt = { reason: cleanReason, key: crypto.randomUUID() };
      submit.disabled = true;
      message.textContent = "Sending to the store team…";
      try {
        const result = await callVisitorApi(`/widget/conversations/${encodeURIComponent(session.conversation_id)}/cancellation-request`, {
          method: "POST",
          headers: { "content-type": "application/json", "idempotency-key": attempt.key },
          body: JSON.stringify({ reason: cleanReason }),
        });
        message.textContent = result.message;
        reason.disabled = true;
        submit.remove();
        attempt = null;
        await loadHistory();
      } catch (error) {
        showCardError(message, error.message || "Could not submit the cancellation request.");
      } finally {
        submit.disabled = false;
      }
    });
    card.append(title, description, reason, submit, message);
    if (after?.parentNode) after.after(card);
    else thread.appendChild(card);
    card.scrollIntoView({ block: "nearest" });
  }

  function showCardError(element, text) {
    element.textContent = text;
    element.classList.add("card-error");
  }

  async function callVisitorApi(path, init = {}) {
    const response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: { ...(init.headers || {}), authorization: `Bearer ${session.visitor_token}` },
      credentials: "omit",
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(safeError(body, "Request could not be completed."));
    return body;
  }

  function trackRecommendationEvent(messageId, eventType, product) {
    if (!session || !messageId) return;
    const productId = product?.product_id || "none";
    const key = `${messageId}:${eventType}:${productId}`;
    let tracked;
    try { tracked = JSON.parse(sessionStorage.getItem(`${sessionKey}:events`) || "{}"); } catch { tracked = {}; }
    if (tracked[key]) return;
    const eventId = crypto.randomUUID();
    tracked[key] = eventId;
    sessionStorage.setItem(`${sessionKey}:events`, JSON.stringify(tracked));
    callVisitorApi(`/widget/conversations/${encodeURIComponent(session.conversation_id)}/recommendation-events`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ event_id: eventId, message_id: messageId, event_type: eventType, ...(product?.product_id ? { product_id: product.product_id } : {}), ...(product?.variant_id ? { variant_id: product.variant_id } : {}) }),
    }).catch(() => {
      delete tracked[key];
      sessionStorage.setItem(`${sessionKey}:events`, JSON.stringify(tracked));
    });
  }

  function readSession() {
    try { session = JSON.parse(sessionStorage.getItem(sessionKey) || "null"); }
    catch { session = null; }
  }

  let streamController = null;
  let streamGeneration = 0;
  let partialRow = null;
  let partialText = "";
  let visibleLength = 0;
  let nextWordAt = 0;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let pendingFinalMessageId = null;
  let firstDeltaExecution = null;
  let streamCursor = "";
  let renderFrame = 0;
  let optimisticRow = null;

  function clearPartial() {
    partialRow?.remove();
    partialRow = null;
    partialText = "";
    visibleLength = 0;
    nextWordAt = 0;
    pendingFinalMessageId = null;
    firstDeltaExecution = null;
    if (renderFrame) cancelAnimationFrame(renderFrame);
    renderFrame = 0;
  }

  function renderPartial() {
    if (!visibleLength) return;
    thread.querySelector(".typing-row")?.remove();
    if (!partialRow) {
      partialRow = addMessage({ sender_type: "assistant", content: "" });
      partialRow.classList.add("streaming-row");
      partialRow.setAttribute("aria-hidden", "true");
    } else if (!partialRow.isConnected) {
      thread.appendChild(partialRow);
    }
    renderAssistantMessage(partialRow.querySelector(".message"), partialText.slice(0, visibleLength), true);
    if (firstDeltaExecution) {
      logStreamTiming("first_dom_update", firstDeltaExecution);
      firstDeltaExecution = null;
    }
    thread.scrollTo({ top: thread.scrollHeight, behavior: "instant" });
  }

  function revealPartial(now) {
    renderFrame = 0;
    if (now >= nextWordAt || reducedMotion.matches) {
      if (reducedMotion.matches) {
        visibleLength = partialText.length;
      } else {
        const words = partialText.slice(visibleLength).match(/\s*\S+\s*|\s+/g) || [];
        // Bound the visual catch-up rate: a buffered network burst must not
        // instantly paint the entire reply and look like non-streaming output.
        for (const word of words.slice(0, STREAM_MAX_WORDS_PER_FRAME)) visibleLength += word.length;
      }
      nextWordAt = now + STREAM_WORD_INTERVAL_MS;
      renderPartial();
    }
    if (visibleLength < partialText.length) {
      renderFrame = requestAnimationFrame(revealPartial);
    } else if (pendingFinalMessageId && !streamController) {
      scheduleHistoryPoll(true);
    }
  }

  function stopReplyStream() {
    streamController?.abort();
    streamController = null;
    streamCursor = "";
    clearPartial();
  }

  function logStreamTiming(stage, executionId) {
    const name = `supportpilot:${executionId}:${stage}`;
    const mark = performance.mark(name);
    console.debug("SupportPilot reply stream", {
      stage, executionId, atMs: Math.round(performance.timeOrigin + mark.startTime),
    });
  }

  function alreadyReadSequence(sequence) {
    if (!streamCursor) return false;
    const [executionId, attempt, offset] = sequence.split(":");
    const [previousExecution, previousAttempt, previousOffset] = streamCursor.split(":");
    if (executionId !== previousExecution) return false;
    if (attempt !== previousAttempt) return Number(attempt) < Number(previousAttempt);
    // A malformed cursor must never crash the widget or accept a replay.
    if (!/^\\d+-\\d+$/.test(offset || "") || !/^\\d+-\\d+$/.test(previousOffset || "")) return true;
    const [time, index] = offset.split("-").map(BigInt);
    const [previousTime, previousIndex] = previousOffset.split("-").map(BigInt);
    return time < previousTime || (time === previousTime && index <= previousIndex);
  }

  function consumeReplyEvent(frame, conversationId) {
    const data = frame.split("\n").find((line) => line.startsWith("data: "));
    if (!data) return false;
    const event = JSON.parse(data.slice(6));
    if (
      event?.conversation_id !== conversationId ||
      typeof event.execution_id !== "string" ||
      typeof event.sequence !== "string" ||
      !event.sequence.startsWith(`${event.execution_id}:`) ||
      !/^[0-9a-f-]{36}:\d{1,5}:\d{1,20}-\d{1,20}$/.test(event.sequence) ||
      typeof event.timestamp !== "string" ||
      !event.payload || typeof event.payload !== "object"
    ) return false;
    // Status events are allowed through for state updates; stale deltas are not.
    if (event.event_type === "message.delta" && alreadyReadSequence(event.sequence)) return false;
    switch (event.event_type) {
      case "execution.queued":
      case "execution.started":
      case "execution.status": {
        // A status frame may be repeated during reconnect. Never erase text
        // already received for the same execution attempt.
        const previousAttempt = streamCursor.split(":").slice(0, 2).join(":");
        const incomingAttempt = event.sequence.split(":").slice(0, 2).join(":");
        if (previousAttempt && previousAttempt !== incomingAttempt) clearPartial();
        // Status offsets (0-0) must not rewind a real Redis delta cursor.
        if (!partialText || previousAttempt !== incomingAttempt) {
          streamCursor = event.sequence;
        }
        if (waitingForAssistant && !partialText && !thread.querySelector(".typing-row")) addTyping();
        return false;
      }
      case "message.delta":
        if (typeof event.payload?.text !== "string" || !event.payload.text) return false;
        if (partialText.length + event.payload.text.length > 16000) throw new Error("Reply stream exceeded its limit");
        if (!partialText) {
          firstDeltaExecution = event.execution_id;
          logStreamTiming("first_browser_delta", event.execution_id);
        }
        streamCursor = event.sequence;
        partialText += event.payload.text;
        if (!renderFrame) renderFrame = requestAnimationFrame(revealPartial);
        return false;
      case "message.completed":
        pendingFinalMessageId = event.payload.message_id || null;
        break;
      case "execution.failed":
      case "execution.cancelled":
      case "conversation.handoff":
        break;
      default:
        return false;
    }
    if (event.event_type !== "message.completed") clearPartial();
    waitingForAssistant = false;
    thread.querySelector(".typing-row")?.remove();
    if (event.event_type === "execution.failed" && !event.payload?.message_id) {
      setStatus("The assistant couldn’t finish its reply. You can send another message.", true);
    } else if (event.event_type === "conversation.handoff") {
      setStatus("A support teammate can follow up here.");
    } else {
      setStatus("");
    }
    return true;
  }

  async function readReplyStream(activeSession, signal) {
    const query = streamCursor ? `?after=${encodeURIComponent(streamCursor)}` : "";
    const response = await fetch(
      `${apiBase}/widget/conversations/${encodeURIComponent(activeSession.conversation_id)}/reply-stream${query}`,
      { headers: { accept: "text/event-stream", authorization: `Bearer ${activeSession.visitor_token}` }, credentials: "omit", signal },
    );
    if (!response.ok || !response.body || !response.headers.get("content-type")?.startsWith("text/event-stream")) return true;
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    try {
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) return false;
        // Keep a trailing CR until the next network chunk: CRLF may be
        // split between reads. Also accept bare CR, permitted by SSE.
        buffer += value;
        const trailingCR = buffer.endsWith("\r");
        const normalized = (trailingCR ? buffer.slice(0, -1) : buffer)
          .replace(/\r\n|\r/g, "\n");
        buffer = normalized + (trailingCR ? "\r" : "");
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) >= 0) {
          const frame = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          if (signal.aborted || consumeReplyEvent(frame, activeSession.conversation_id)) return true;
        }
        if (buffer.length > 64000) throw new Error("Reply stream frame exceeded its limit");
      }
      return true;
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  function canPollHistory() {
    return session && !streamController && !pending &&
      document.visibilityState === "visible" && panel.classList.contains("open");
  }

  function stopHistoryPolling() {
    clearTimeout(historyTimer);
    historyTimer = undefined;
    historyPollController?.abort();
  }

  function scheduleHistoryPoll(immediate = false) {
    clearTimeout(historyTimer);
    historyTimer = undefined;
    if (!canPollHistory() || historyPollController) return;
    const interval = pendingFinalMessageId ? FINAL_HISTORY_REFRESH_MS
      : waitingForAssistant ? ACTIVE_HISTORY_REFRESH_MS : IDLE_HISTORY_REFRESH_MS;
    const retryDelay = Math.min(interval * 2 ** historyPollFailures, MAX_HISTORY_RETRY_MS);
    historyTimer = setTimeout(async () => {
      historyTimer = undefined;
      if (!canPollHistory()) return;
      const controller = new AbortController();
      historyPollController = controller;
      try {
        await loadHistory({ idleOnly: true, signal: controller.signal });
        historyPollFailures = 0;
      } catch {
        if (!controller.signal.aborted) historyPollFailures = Math.min(historyPollFailures + 1, 5);
      } finally {
        historyPollController = undefined;
        scheduleHistoryPoll();
      }
    }, immediate ? 0 : retryDelay);
  }

  async function startReplyStream() {
    if (!waitingForAssistant || !config?.streaming_enabled || !session || streamController || !panel.classList.contains("open")) return;
    stopHistoryPolling();
    const activeSession = session;
    const controller = new AbortController();
    streamController = controller;
    streamGeneration++;
    try {
      for (let retry = 0; retry < 4 && !controller.signal.aborted; retry++) {
        let terminal = false;
        try {
          terminal = await readReplyStream(activeSession, controller.signal);
        } catch (error) {
          if (controller.signal.aborted) return;
          if (error instanceof SyntaxError) break;
        }
        if (terminal || controller.signal.aborted || !waitingForAssistant) break;
        // Bound reconnect pressure while preserving the Redis replay cursor.
        await new Promise((resolve) => setTimeout(resolve, Math.min(250 * 2 ** retry, 1500)));
      }
    } finally {
      if (streamController === controller) {
        streamController = null;
        streamCursor = "";
        if (panel.classList.contains("open") && document.visibilityState === "visible") {
          await loadHistory({ idleOnly: true }).catch(() => {});
        }
        scheduleHistoryPoll();
      }
    }
  }

  async function loadHistory({ idleOnly = false, signal } = {}) {
    if (!session || (idleOnly && streamController)) return;
    const generationAtRequest = streamGeneration;
    const response = await fetch(`${apiBase}/widget/conversations/${encodeURIComponent(session.conversation_id)}`, {
      headers: { authorization: `Bearer ${session.visitor_token}` },
      credentials: "omit",
      signal,
    });
    if (!response.ok) throw new Error("Could not load this chat. Start a new conversation.");
    const result = await response.json();
    // A poll that started before the stream must not overwrite its partial row.
    if (signal?.aborted || (idleOnly && (streamController || streamGeneration !== generationAtRequest))) return;
    // A terminal frame may arrive in the same network burst as its text.
    // Keep the preview visible until the words already received have been shown.
    if (pendingFinalMessageId && result.ai_mode === "ai" && visibleLength < partialText.length &&
        !reducedMotion.matches && document.visibilityState === "visible") return;
    const previousLatestMessageId = latestMessages.at(-1)?.id;
    latestMessages = result.messages || [];
    verifiedOrder = Boolean(result.order_verified);
    conversationMode = result.ai_mode === "ai" ? "ai" : "human";
    if (conversationMode !== "ai" && waitingForAssistant) {
      waitingForAssistant = false;
      assistantWaitStartedAt = 0;
      setStatus("Message sent. A support teammate will follow up here.");
    } else if (waitingForAssistant && Date.now() - assistantWaitStartedAt > 45000) {
      clearPartial();
      waitingForAssistant = false;
      assistantWaitStartedAt = 0;
      setStatus("The reply is taking longer than expected. A support teammate can follow up here.");
    }
    if (pendingFinalMessageId && latestMessages.some((message) => message.id === pendingFinalMessageId)) {
      clearPartial();
    } else if (conversationMode !== "ai") {
      clearPartial();
    }
    const signature = JSON.stringify([
      verifiedOrder,
      conversationMode,
      latestMessages.map(({ id, updated_at, created_at, content, verification_required, verification_paused }) =>
        [id, updated_at, created_at, content, verification_required, verification_paused]
      ),
    ]);
    if (signature === lastHistorySignature) {
      if (!waitingForAssistant) thread.querySelector(".typing-row")?.remove();
      return;
    }
    lastHistorySignature = signature;
    const assistantBefore = thread.querySelectorAll(".message-row.assistant:not(.typing-row):not(.streaming-row)").length;
    thread.replaceChildren();
    if (!latestMessages.length) addWelcome();
    const latestRecommendation = [...latestMessages].reverse().find(
      (message) => message.recommendation?.response_type,
    );
    const lastRecommendationId = latestRecommendation?.id || null;
    if (lastRecommendationId !== lastRecommendationMessageId) {
      compareSelections = [];
      lastRecommendationMessageId = lastRecommendationId;
    }
    latestMessages.forEach((message) => addMessage(message, {
      canCompare: message.id === lastRecommendationId && message.recommendation?.response_type === "recommendations",
    }));
    const assistantAfter = thread.querySelectorAll(".message-row.assistant:not(.typing-row):not(.streaming-row)").length;
    if (optimisticRow) {
      const persisted = latestMessages.some((message) =>
        message.sender_type === "customer" && !optimisticRow.previousIds.has(message.id) &&
        message.content === optimisticRow.content
      );
      if (persisted) optimisticRow = null;
      else thread.appendChild(optimisticRow.element);
    }
    const latestMessage = latestMessages.at(-1);
    if (!pendingFinalMessageId && waitingForAssistant && latestMessage?.sender_type === "assistant" &&
        (assistantAfter > assistantBefore || latestMessage.id !== previousLatestMessageId)) {
      stopReplyStream();
      waitingForAssistant = false;
      assistantWaitStartedAt = 0;
    }
    const verificationRequested = latestAssistantRequestsVerification(latestMessages);
    if (partialText) renderPartial();
    const latestPublicMessage = latestMessage;
    const latestSupportMessage = latestMessages.findLast((message) => message.sender_type !== "customer");
    const verificationPaused = latestSupportMessage?.verification_paused === true;
    const verificationRequired = latestPublicMessage?.verification_required === true;
    // Order words in a customer message are not enough to open the private
    // verification form. Let the assistant first understand the request and
    // explicitly ask for verification; otherwise ordinary questions about
    // ordering, returns, or store policies get interrupted by a generic form.
    const needsOrderVerification = !verificationPaused && !cancellationWasSubmitted(latestMessages) && (
      verificationRequired || (
        verificationRequested && !/refund request/i.test(latestPublicMessage?.content || "")
      )
    );
    if (waitingForAssistant && conversationMode === "ai" && config?.ai_enabled && !needsOrderVerification) {
      const latestCustomer = [...latestMessages].reverse().find((item) => item.sender_type === "customer")?.content || "";
      if (/\b(recommend|suggest|phone|smartphone|mobile|laptop|camera|budget|compare|better|only)\b/i.test(latestCustomer) && window.SupportPilotRecommendationUI) {
        const loading = window.SupportPilotRecommendationUI.RecommendationLoadingState();
        loading.classList.add("recommendation-message");
        thread.appendChild(loading);
      } else {
        addTyping();
      }
    }
    if (needsOrderVerification) {
      waitingForAssistant = false;
      addOrderVerificationCard();
      setStatus("Enter your order number and checkout email to continue securely.");
    } else if (!verificationPaused && verifiedOrder && containsCancellationIntent(latestMessages) && !cancellationWasSubmitted(latestMessages)) {
      addCancellationCard("your verified order");
    }
    if (assistantAfter > 0) setStatus("");
    thread.scrollTop = thread.scrollHeight;
  }

  async function ensureConfig() {
    if (config) return config;
    await loadRecommendationUI();
    const response = await fetch(`${apiBase}/widget/${encodeURIComponent(publicId)}/config`, { credentials: "omit" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(safeError(body, "Chat is unavailable for this store."));
    config = body;
    conversationMode = config.ai_enabled ? "ai" : "human";
    shadow.querySelector(".store-name").textContent = config.store_name || "Store support";
    shadow.querySelector(".assistant-name").textContent = config.assistant_name || "AI support assistant";
    shadow.querySelector(".brand-mark").textContent = (config.store_name || "S").trim().slice(0, 1).toUpperCase();
    shadow.querySelector(".availability-text").textContent = "Chat available";
    return config;
  }

  async function openChat() {
    try {
      await ensureConfig();
      readSession();
      panel.classList.add("open");
      panel.setAttribute("aria-hidden", "false");
      launcher.setAttribute("aria-expanded", "true");
      launcher.hidden = true;
      if (session) {
        await loadHistory();
        if (waitingForAssistant) void startReplyStream();
        scheduleHistoryPoll();
      } else if (!thread.childElementCount) {
        addWelcome();
      }
      compose.focus({ preventScroll: true });
      setStatus("");
    } catch (error) {
      panel.classList.add("open");
      panel.setAttribute("aria-hidden", "false");
      launcher.hidden = true;
      setStatus(error.message || "Chat is unavailable.", true);
    }
  }

  function closeChat() {
    stopHistoryPolling();
    stopReplyStream();
    panel.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
    launcher.hidden = false;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  }

  function makeFirstAttempt(body) {
    const digestInput = JSON.stringify(body);
    if (firstAttempt?.body === digestInput) return firstAttempt;
    try {
      const pendingAttempt = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
      if (pendingAttempt?.body === digestInput && typeof pendingAttempt.key === "string") {
        firstAttempt = pendingAttempt;
        return firstAttempt;
      }
    } catch { /* discard malformed retry metadata */ }
    firstAttempt = { body: digestInput, key: crypto.randomUUID() };
    sessionStorage.setItem(pendingKey, JSON.stringify(firstAttempt));
    return firstAttempt;
  }

  async function sendMessage() {
    const content = compose.value.trim();
    if (!content || pending) return;
    pending = true;
    stopHistoryPolling();
    sendButton.disabled = true;
    setStatus("Sending…");
    stopReplyStream();
    thread.querySelector(".welcome")?.remove();
    optimisticRow = {
      element: addMessage({ sender_type: "customer", content, created_at: new Date().toISOString() }),
      content,
      previousIds: new Set(latestMessages.map((message) => message.id)),
    };
    thread.scrollTop = thread.scrollHeight;
    try {
      await ensureConfig();
      readSession();
      const website = "";
      if (!session) {
        const body = { content, visitor_name: null, visitor_email: null, contact_consent: false, website };
        const attempt = makeFirstAttempt(body);
        const response = await fetch(`${apiBase}/widget/${encodeURIComponent(publicId)}/messages`, {
          method: "POST",
          headers: { "content-type": "application/json", "idempotency-key": attempt.key },
          body: JSON.stringify(body),
          credentials: "omit",
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(safeError(result, "Could not send your message."));
        session = { conversation_id: result.conversation_id, visitor_token: result.visitor_token };
        sessionStorage.setItem(sessionKey, JSON.stringify(session));
        sessionStorage.removeItem(pendingKey);
        firstAttempt = null;
      } else {
        const selectionSignature = JSON.stringify(nextRecommendationSelections || []);
        const attempt = followingAttempt?.content === content && followingAttempt.selectionSignature === selectionSignature
          ? followingAttempt
          : { content, selectionSignature, key: crypto.randomUUID() };
        followingAttempt = attempt;
        const messageBody = { content, website };
        if (nextRecommendationSelections) messageBody.recommendation_selections = nextRecommendationSelections;
        await callVisitorApi(`/widget/conversations/${encodeURIComponent(session.conversation_id)}/messages`, {
          method: "POST",
          headers: { "content-type": "application/json", "idempotency-key": attempt.key },
          body: JSON.stringify(messageBody),
        });
        followingAttempt = null;
        nextRecommendationSelections = null;
        compareSelections = [];
      }
      compose.value = "";
      resizeComposer();
      waitingForAssistant = Boolean(config?.ai_enabled && conversationMode === "ai");
      assistantWaitStartedAt = waitingForAssistant ? Date.now() : 0;
      setStatus(waitingForAssistant ? "Your assistant is thinking…" : "Message sent. A support teammate will follow up here.");
      void startReplyStream();
      await loadHistory({ idleOnly: true });
    } catch (error) {
      optimisticRow?.element.remove();
      optimisticRow = null;
      const errorText = error.message || "Could not send your message. Please try again.";
      setStatus(errorText, true);
      if (/\b(recommend|suggest|phone|smartphone|mobile|laptop|camera|budget|compare|better|only)\b/i.test(content) && window.SupportPilotRecommendationUI) {
        thread.querySelector(".recommendation-error")?.remove();
        const errorState = window.SupportPilotRecommendationUI.RecommendationErrorState(errorText, sendMessage);
        errorState.classList.add("recommendation-message");
        thread.appendChild(errorState);
        errorState.scrollIntoView({ block: "nearest" });
      }
    } finally {
      if (!session && !thread.childElementCount) addWelcome();
      pending = false;
      scheduleHistoryPoll();
      sendButton.disabled = !compose.value.trim();
    }
  }

  function resizeComposer() {
    compose.style.height = "auto";
    compose.style.height = `${Math.min(compose.scrollHeight, 115)}px`;
    sendButton.disabled = !compose.value.trim() || pending;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") stopHistoryPolling();
    else scheduleHistoryPoll(true);
  });
  launcher.addEventListener("click", openChat);
  shadow.querySelector(".close").addEventListener("click", closeChat);
  shadow.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && panel.classList.contains("open")) closeChat();
    if (event.key === "Enter" && !event.shiftKey && event.target === compose) {
      event.preventDefault();
      sendMessage();
    }
  });
  compose.addEventListener("input", resizeComposer);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });
})();
