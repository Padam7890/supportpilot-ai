(() => {
  const script = document.currentScript;
  const publicId = script?.getAttribute("data-widget-id");
  if (!publicId) {
    console.error("[SupportPilot widget] Missing data-widget-id; chat launcher was not mounted.");
    return;
  }
  let apiBase = (script.getAttribute("data-api-base") || new URL("/api", script.src).href).replace(/\/$/, "");
  // Keep existing snippets working after moving from the old `/api/widget` base.
  if (apiBase.endsWith("/api/widget")) apiBase = apiBase.slice(0, -"/widget".length);
  const sessionKey = `supportpilot-widget-session:${publicId}`;
  const pendingKey = `supportpilot-widget-pending:${publicId}`;
  const host = document.createElement("div");
  host.id = "supportpilot-widget-host";
  host.style.cssText = "display:block!important;visibility:visible!important;opacity:1!important;pointer-events:auto!important;position:fixed!important;right:20px!important;bottom:20px!important;z-index:2147483000!important;font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif!important;color:#172033!important";
  const shadow = host.attachShadow({ mode: "closed" });
  shadow.innerHTML = `<style>
    *{box-sizing:border-box}button,input,textarea{font:inherit}.launcher{border:0;border-radius:999px;background:#1749e8;color:#fff;padding:14px 18px;box-shadow:0 8px 24px #071a4d33;cursor:pointer;font-weight:700}.panel{display:none;width:min(360px,calc(100vw - 32px));height:min(540px,calc(100dvh - 100px));margin-bottom:12px;background:white;border:1px solid #dbe2ed;border-radius:18px;box-shadow:0 16px 48px #071a4d33;overflow:hidden}.panel.open{display:flex;flex-direction:column}.head{background:#1749e8;color:white;padding:16px 18px;font-weight:700;display:flex;justify-content:space-between;align-items:center}.close{background:transparent;color:white;border:0;font-size:22px;cursor:pointer}.thread{flex:1;overflow:auto;padding:14px;background:#f7f9fc}.bubble{max-width:88%;padding:10px 12px;margin:8px 0;border-radius:14px;white-space:pre-wrap;overflow-wrap:anywhere}.customer{background:#e9eef8;border-bottom-left-radius:4px}.agent{background:#dce8ff;margin-left:auto;border-bottom-right-radius:4px}.form{padding:12px;border-top:1px solid #e6eaf0;display:grid;gap:8px}.form input,.form textarea{width:100%;border:1px solid #ccd5e2;border-radius:9px;padding:9px 10px;color:#172033}.form textarea{resize:vertical;min-height:70px}.honeypot{position:absolute!important;left:-10000px!important;width:1px!important;height:1px!important;opacity:0!important}.consent{display:flex;align-items:flex-start;gap:7px;font-size:11px;color:#596579}.consent input{width:auto;margin-top:2px}.send{border:0;border-radius:9px;background:#1749e8;color:white;padding:10px;font-weight:700;cursor:pointer}.send:disabled{opacity:.5;cursor:wait}.status{font-size:12px;color:#596579;min-height:16px}.status.error{color:#b42336}.thanks{text-align:center;padding:12px;color:#40516a;font-size:12px}
  </style><section class="panel" role="dialog" aria-label="Customer support chat" aria-modal="false"><header class="head"><span class="brand">Support</span><button class="close" aria-label="Close chat">×</button></header><div class="thread" aria-live="polite"></div><form class="form"><div class="contact"></div><input class="honeypot" name="website" tabindex="-1" autocomplete="off" aria-hidden="true"><textarea name="content" aria-label="Your message" maxlength="4000" placeholder="Write your message…" required></textarea><label class="consent-wrap" hidden><span class="consent"><input name="consent" type="checkbox"><span>If I provide my name or email, I consent to the store using it to respond to this request.</span></span></label><p class="status" role="status"></p><button class="send" type="submit">Send message</button><div class="thanks">A support teammate will reply here.</div></form></section><button class="launcher" aria-expanded="false">Chat with us</button>`;
  (document.body || document.documentElement).appendChild(host);

  const panel = shadow.querySelector(".panel");
  const launcher = shadow.querySelector(".launcher");
  const thread = shadow.querySelector(".thread");
  const form = shadow.querySelector("form");
  const contact = shadow.querySelector(".contact");
  const consentWrap = shadow.querySelector(".consent-wrap");
  const status = shadow.querySelector(".status");
  const sendButton = shadow.querySelector(".send");
  let config;
  let session;
  let polling;
  let firstAttempt;
  let followingAttempt;

  function setStatus(message, error = false) {
    status.textContent = message;
    status.classList.toggle("error", error);
  }

  function addMessage(message) {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${["agent", "assistant"].includes(message.sender_type) ? "agent" : "customer"}`;
    bubble.textContent = message.content;
    thread.appendChild(bubble);
    thread.scrollTop = thread.scrollHeight;
  }

  function readSession() {
    try { session = JSON.parse(sessionStorage.getItem(sessionKey) || "null"); } catch { session = null; }
  }

  async function loadHistory() {
    if (!session) return;
    const response = await fetch(`${apiBase}/widget/conversations/${encodeURIComponent(session.conversation_id)}`, {
      headers: { Authorization: `Bearer ${session.visitor_token}` },
      credentials: "omit",
    });
    if (!response.ok) throw new Error("Could not load this chat. Start a new conversation.");
    const result = await response.json();
    thread.replaceChildren();
    result.messages.forEach(addMessage);
  }

  async function openChat() {
    panel.classList.add("open");
    launcher.setAttribute("aria-expanded", "true");
    launcher.hidden = true;
    try {
      if (!config) {
        const response = await fetch(`${apiBase}/widget/${encodeURIComponent(publicId)}/config`, { credentials: "omit" });
        if (!response.ok) throw new Error("Chat is unavailable for this store.");
        config = await response.json();
        shadow.querySelector(".brand").textContent = config.store_name;
        shadow.querySelector(".head").setAttribute("aria-label", `${config.store_name} support`);
        if (config.collect_contact) {
          contact.innerHTML = `<input name="visitor_name" maxlength="120" autocomplete="name" aria-label="Your name (optional)" placeholder="Your name (optional)"><input name="visitor_email" type="email" maxlength="254" autocomplete="email" aria-label="Email (optional)" placeholder="Email for a reply (optional)">`;
          consentWrap.hidden = false;
        }
      }
      readSession();
      if (session) {
        form.querySelector("textarea").placeholder = "Continue the conversation…";
        await loadHistory();
        if (!polling) polling = setInterval(() => { if (document.visibilityState === "visible" && panel.classList.contains("open")) loadHistory().catch(() => {}); }, 7000);
      } else if (!thread.childElementCount) {
        const welcome = document.createElement("p");
        welcome.className = "thanks";
        welcome.textContent = config.welcome_message;
        thread.appendChild(welcome);
      }
      setStatus("");
    } catch (error) {
      setStatus(error.message || "Chat is unavailable.", true);
    }
  }

  launcher.addEventListener("click", openChat);
  shadow.querySelector(".close").addEventListener("click", () => {
    panel.classList.remove("open");
    launcher.hidden = false;
    launcher.setAttribute("aria-expanded", "false");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = new FormData(form);
    const content = String(values.get("content") || "").trim();
    if (!content) return;
    const name = String(values.get("visitor_name") || "").trim();
    const email = String(values.get("visitor_email") || "").trim();
    const consent = Boolean(values.get("consent"));
    const website = String(values.get("website") || "");
    if (!session && (name || email) && !consent) return setStatus("Please consent before sharing contact details.", true);
    sendButton.disabled = true;
    setStatus("Sending…");
    try {
      if (!session) {
        const body = { content, visitor_name: name || null, visitor_email: email || null, contact_consent: consent, website };
        const bodyHash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(body)));
        const digest = Array.from(new Uint8Array(bodyHash), (byte) => byte.toString(16).padStart(2, "0")).join("");
        if (!firstAttempt) {
          try {
            const pending = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
            if (pending?.digest === digest && typeof pending.key === "string") firstAttempt = pending;
          } catch { firstAttempt = null; }
        }
        if (!firstAttempt || firstAttempt.digest !== digest) {
          firstAttempt = { digest, key: crypto.randomUUID() };
          sessionStorage.setItem(pendingKey, JSON.stringify(firstAttempt));
        }
        const response = await fetch(`${apiBase}/widget/${encodeURIComponent(publicId)}/messages`, {
          method: "POST",
          headers: { "content-type": "application/json", "idempotency-key": firstAttempt.key },
          body: JSON.stringify(body),
          credentials: "omit",
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Could not send your message.");
        session = { conversation_id: result.conversation_id, visitor_token: result.visitor_token };
        sessionStorage.setItem(sessionKey, JSON.stringify(session));
        sessionStorage.removeItem(pendingKey);
        firstAttempt = null;
        form.reset();
        form.querySelector("textarea").placeholder = "Continue the conversation…";
        await loadHistory();
        setStatus(result.confirmation);
        if (!polling) polling = setInterval(() => { if (document.visibilityState === "visible" && panel.classList.contains("open")) loadHistory().catch(() => {}); }, 7000);
      } else {
        followingAttempt ??= { content, key: crypto.randomUUID() };
        if (followingAttempt.content !== content) followingAttempt = { content, key: crypto.randomUUID() };
        const response = await fetch(`${apiBase}/widget/conversations/${encodeURIComponent(session.conversation_id)}/messages`, {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${session.visitor_token}`, "idempotency-key": followingAttempt.key },
          body: JSON.stringify({ content, website }),
          credentials: "omit",
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Could not send your message.");
        followingAttempt = null;
        form.querySelector("textarea").value = "";
        await loadHistory();
        setStatus("Message sent.");
      }
    } catch (error) {
      setStatus(error.message || "Could not send your message. Please try again.", true);
    } finally {
      sendButton.disabled = false;
    }
  });
})();
