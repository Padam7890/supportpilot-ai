import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const TENANT_ACCESS_COOKIE = "supportpilot_access";
const TENANT_REFRESH_COOKIE = "supportpilot_refresh";
const PLATFORM_ACCESS_COOKIE = "supportpilot_platform_access";
const PLATFORM_REFRESH_COOKIE = "supportpilot_platform_refresh";
const TENANT_CHALLENGE_COOKIE = "supportpilot_auth_challenge";
/** Must cover backend refresh JWT lifetime (`refresh_token_expire_days`); default 30d matches backend Settings. */
const REFRESH_MAX_AGE = Number(process.env.AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS ?? 60 * 60 * 24 * 30);
const AUTH_CHALLENGE_MAX_AGE = 60 * 10;
const backendUrl = (process.env.BACKEND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user?: unknown;
  platform_owner?: unknown;
};

function isTokenResponse(body: Record<string, unknown>): body is TokenResponse {
  return typeof body.access_token === "string" && typeof body.refresh_token === "string";
}

function sessionResponseFromTokens(tokens: TokenResponse, status: number, platform: boolean) {
  const response = NextResponse.json(
    platform ? { platform_owner: tokens.platform_owner } : { user: tokens.user },
    { status },
  );
  setSessionCookies(response, tokens, platform);
  clearAuthChallengeCookie(response);
  return response;
}

/**
 * When many tabs or parallel queries hit 401 together, each would call `/auth/refresh` with the same
 * refresh cookie. The backend rotates refresh tokens and treats a second concurrent refresh as
 * reuse — revoking sessions and forcing sign-in. Coalesce in-flight refresh by refresh token + realm.
 */
const refreshInflight = new Map<string, Promise<TokenResponse>>();

function refreshCoalesceKey(platform: boolean, refreshToken: string) {
  const realm = platform ? "platform" : "tenant";
  const tail = refreshToken.slice(-24);
  return `${realm}:${tail.length}:${tail}`;
}

function runSingleFlightRefresh(
  request: NextRequest,
  correlationId: string,
  platform: boolean,
  refreshToken: string,
): Promise<TokenResponse> {
  const key = refreshCoalesceKey(platform, refreshToken);
  const existing = refreshInflight.get(key);
  if (existing) return existing;

  const refreshPath = platform ? "platform/auth/refresh" : "auth/refresh";
  const promise = (async () => {
    const refreshResponse = await requestBackend(
      request,
      refreshPath,
      correlationId,
      undefined,
      JSON.stringify({ refresh_token: refreshToken }),
      "POST",
    );
    const raw = await refreshResponse.text();
    if (!refreshResponse.ok) {
      throw new Error(raw || `refresh_failed_${refreshResponse.status}`);
    }
    return JSON.parse(raw) as TokenResponse;
  })();

  refreshInflight.set(key, promise);
  const clearRefresh = () => {
    refreshInflight.delete(key);
  };
  void promise.then(clearRefresh, clearRefresh);
  return promise;
}

function setSessionCookies(response: NextResponse, tokens: TokenResponse, platform: boolean) {
  const secure = process.env.NODE_ENV === "production";
  const accessCookie = platform ? PLATFORM_ACCESS_COOKIE : TENANT_ACCESS_COOKIE;
  const refreshCookie = platform ? PLATFORM_REFRESH_COOKIE : TENANT_REFRESH_COOKIE;
  response.cookies.set(accessCookie, tokens.access_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: tokens.expires_in,
  });
  response.cookies.set(refreshCookie, tokens.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  });
}

function clearSessionCookies(response: NextResponse, platform: boolean) {
  const common = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: 0,
  };
  response.cookies.set(platform ? PLATFORM_ACCESS_COOKIE : TENANT_ACCESS_COOKIE, "", common);
  response.cookies.set(platform ? PLATFORM_REFRESH_COOKIE : TENANT_REFRESH_COOKIE, "", common);
}

function setAuthChallengeCookie(response: NextResponse, token: string) {
  response.cookies.set(TENANT_CHALLENGE_COOKIE, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: AUTH_CHALLENGE_MAX_AGE,
  });
}

function clearAuthChallengeCookie(response: NextResponse) {
  response.cookies.set(TENANT_CHALLENGE_COOKIE, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
}

function isMutation(method: string) {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

function hasSameOrigin(request: NextRequest) {
  // In Compose or behind a reverse proxy, request.url can contain Next's
  // internal hostname instead of the browser-facing host. Compare against
  // the incoming host headers as well so legitimate browser requests pass
  // while cross-site Origins still fail closed.
  const requestUrl = new URL(request.url);
  const forwardedHost = request.headers.get("x-forwarded-host")?.split(",")[0]?.trim();
  const host = request.headers.get("host")?.trim();
  const forwardedProto = request.headers
    .get("x-forwarded-proto")
    ?.split(",")[0]
    ?.trim()
    .replace(/:$/, "");
  const protocols = new Set([requestUrl.protocol.slice(0, -1)]);
  if (forwardedProto === "http" || forwardedProto === "https") protocols.add(forwardedProto);

  const expectedOrigins = new Set([requestUrl.origin]);
  for (const candidateHost of [forwardedHost, host]) {
    if (!candidateHost) continue;
    for (const protocol of protocols) {
      try {
        expectedOrigins.add(new URL(`${protocol}://${candidateHost}`).origin);
      } catch {
        // Ignore malformed proxy headers; the request URL remains the fallback.
      }
    }
  }

  const origin = request.headers.get("origin");
  if (origin) {
    try {
      return expectedOrigins.has(new URL(origin).origin);
    } catch {
      return false;
    }
  }
  const referer = request.headers.get("referer");
  if (!referer) return false;
  try {
    return expectedOrigins.has(new URL(referer).origin);
  } catch {
    return false;
  }
}

function responseFromUpstream(response: Response, body: string, correlationId: string) {
  const headers = new Headers({
    "content-type": response.headers.get("content-type") ?? "application/json",
    "cache-control": "no-store",
    "x-correlation-id": response.headers.get("x-correlation-id") ?? correlationId,
  });
  const location = response.headers.get("location");
  if (location) headers.set("location", location);
  return new NextResponse(body || null, {
    status: response.status,
    headers,
  });
}

function fileResponseFromUpstream(response: Response, correlationId: string, isKnowledgePdf: boolean) {
  const headers = new Headers({
    "content-type": isKnowledgePdf ? "application/pdf" : "application/octet-stream",
    "cache-control": "private, no-store",
    "x-content-type-options": "nosniff",
    "x-correlation-id": response.headers.get("x-correlation-id") ?? correlationId,
  });
  const disposition = response.headers.get("content-disposition");
  if (disposition) headers.set("content-disposition", disposition);
  if (isKnowledgePdf) {
    headers.set("content-security-policy", "default-src 'none'; frame-ancestors 'self'");
    headers.set("x-frame-options", "SAMEORIGIN");
  }
  return new NextResponse(response.body, { status: response.status, headers });
}

function eventStreamResponseFromUpstream(response: Response, correlationId: string) {
  const headers = new Headers({
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    "x-accel-buffering": "no",
    "x-correlation-id": response.headers.get("x-correlation-id") ?? correlationId,
  });
  return new NextResponse(response.body, { status: response.status, headers });
}

function localProblem(
  request: NextRequest,
  status: number,
  detail: string,
  code: string,
  correlationId: string,
) {
  const title = status === 403 ? "Forbidden" : status === 413 ? "Content Too Large" : "Bad Gateway";
  const problem = {
    type: `urn:supportpilot:problem:${code}`,
    title,
    status,
    detail,
    instance: new URL(request.url).pathname,
    code,
    correlation_id: correlationId,
  };
  return new NextResponse(JSON.stringify(problem), {
    status,
    headers: {
      "content-type": "application/problem+json",
      "cache-control": "no-store",
      "x-correlation-id": correlationId,
    },
  });
}

async function requestBackend(
  request: NextRequest,
  path: string,
  correlationId: string,
  accessToken?: string,
  body?: BodyInit,
  method = request.method,
) {
  const isHealthCheck = path === "health/ready" || path === "health/live" || path === "health/worker";
  const upstreamPath = isHealthCheck ? `/${path}` : `/api/v1/${path}`;
  const upstreamUrl = `${backendUrl}${upstreamPath}${new URL(request.url).search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  else if (body && !["GET", "HEAD"].includes(method)) headers.set("content-type", "application/json");
  headers.set("accept", path === "notifications/stream" ? "text/event-stream" : "application/json");
  headers.set("x-correlation-id", correlationId);
  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  return fetch(upstreamUrl, {
    method,
    headers,
    body: ["GET", "HEAD"].includes(method) ? undefined : body,
    cache: "no-store",
    redirect: "manual",
  });
}

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const correlationId = crypto.randomUUID();
  if (isMutation(request.method) && !hasSameOrigin(request)) {
    return localProblem(
      request,
      403,
      "Cross-origin request rejected",
      "cross_origin_rejected",
      correlationId,
    );
  }
  const { path: segments } = await context.params;
  const path = segments.map(encodeURIComponent).join("/");
  const normalizedPath = `/${path}`;
  const isKnowledgePdf = /^knowledge\/documents\/[^/]+\/pdf$/.test(path);
  const isFileResponse = (request.method === "GET" && path.endsWith("/download"))
    || (isKnowledgePdf && ["GET", "HEAD"].includes(request.method));
  const platform = normalizedPath.startsWith("/platform/");
  const isTenantLogin = normalizedPath === "/auth/login";
  const isTenantRegister = normalizedPath === "/auth/register";
  const isAcceptInvite = normalizedPath === "/auth/invitations/accept";
  const isTenantRefresh = normalizedPath === "/auth/refresh";
  const isTenantLogout = normalizedPath === "/auth/logout";
  const isRegistrationVerify = normalizedPath === "/auth/register/verify-email";
  const isLoginVerify = normalizedPath === "/auth/login/verify-code";
  const isLoginWorkspace = normalizedPath === "/auth/login/select-workspace";
  const isAuthResend = normalizedPath === "/auth/resend-code";
  const isPasswordResetRequest = normalizedPath === "/auth/password-reset/request";
  const isPasswordResetComplete = normalizedPath === "/auth/password-reset/complete";
  const isPlatformLogin = normalizedPath === "/platform/auth/login";
  const isPlatformRefresh = normalizedPath === "/platform/auth/refresh";
  const isPlatformLogout = normalizedPath === "/platform/auth/logout";
  const isLogin = isTenantLogin || isPlatformLogin;
  const isRefresh = isTenantRefresh || isPlatformRefresh;
  const isLogout = isTenantLogout || isPlatformLogout;
  const cookieStore = await cookies();
  const accessCookie = platform ? PLATFORM_ACCESS_COOKIE : TENANT_ACCESS_COOKIE;
  const refreshCookie = platform ? PLATFORM_REFRESH_COOKIE : TENANT_REFRESH_COOKIE;
  const refreshToken = cookieStore.get(refreshCookie)?.value;
  const accessToken = cookieStore.get(accessCookie)?.value;
  const authChallenge = cookieStore.get(TENANT_CHALLENGE_COOKIE)?.value;
  const isAuthStart = isTenantLogin || isTenantRegister || isAcceptInvite || isPasswordResetRequest;
  const needsAuthChallenge = isRegistrationVerify || isLoginVerify || isLoginWorkspace || isAuthResend || isPasswordResetComplete;

  let requestBody: BodyInit | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      requestBody = await request.text();
    } else {
      const declaredLength = Number(request.headers.get("content-length") ?? 0);
      if (declaredLength > 20 * 1024 * 1024) {
        return localProblem(request, 413, "Document exceeds the 20 MB upload limit", "upload_too_large", correlationId);
      }
      const binaryBody = await request.arrayBuffer();
      if (binaryBody.byteLength > 20 * 1024 * 1024) {
        return localProblem(request, 413, "Document exceeds the 20 MB upload limit", "upload_too_large", correlationId);
      }
      requestBody = binaryBody;
    }
  }
  if (isRefresh || isLogout) {
    requestBody = JSON.stringify({ refresh_token: refreshToken ?? "" });
  }
  if (needsAuthChallenge) {
    if (!authChallenge) {
      return localProblem(request, 401, "Sign-in verification expired. Start again.", "auth_challenge_expired", correlationId);
    }
    if (typeof requestBody !== "string") {
      return localProblem(request, 400, "A JSON request body is required", "invalid_request", correlationId);
    }
    try {
      const challengeBody = JSON.parse(requestBody) as Record<string, unknown>;
      requestBody = JSON.stringify({ ...challengeBody, challenge_token: authChallenge });
    } catch {
      return localProblem(request, 400, "Invalid JSON request body", "invalid_request", correlationId);
    }
  }

  try {
    if (isLogout) {
      if (refreshToken) await requestBackend(request, path, correlationId, undefined, requestBody);
      const response = NextResponse.json({ status: "signed_out" });
      clearSessionCookies(response, platform);
      return response;
    }

    let upstream = await requestBackend(
      request,
      path,
      correlationId,
      isLogin || isRefresh || isAuthStart || needsAuthChallenge ? undefined : accessToken,
      requestBody,
    );
    if (isAuthStart) {
      const raw = await upstream.text();
      if (!upstream.ok) {
        const response = responseFromUpstream(upstream, raw, correlationId);
        clearAuthChallengeCookie(response);
        return response;
      }
      const body = JSON.parse(raw) as Record<string, unknown>;
      if (isTenantLogin && isTokenResponse(body)) {
        return sessionResponseFromTokens(body, upstream.status, false);
      }
      const challengeToken = typeof body.challenge_token === "string" ? body.challenge_token : null;
      delete body.challenge_token;
      const response = NextResponse.json(body, { status: upstream.status });
      if (challengeToken) setAuthChallengeCookie(response, challengeToken);
      else clearAuthChallengeCookie(response);
      if (isTenantRegister) clearSessionCookies(response, false);
      return response;
    }
    if (isLoginVerify) {
      const raw = await upstream.text();
      if (!upstream.ok) return responseFromUpstream(upstream, raw, correlationId);
      const tokens = JSON.parse(raw) as TokenResponse;
      return sessionResponseFromTokens(tokens, upstream.status, false);
    }
    if (isLoginWorkspace) {
      const raw = await upstream.text();
      if (!upstream.ok) return responseFromUpstream(upstream, raw, correlationId);
      const body = JSON.parse(raw) as Record<string, unknown>;
      if (isTokenResponse(body)) {
        return sessionResponseFromTokens(body, upstream.status, false);
      }
      return NextResponse.json(body, { status: upstream.status });
    }
    if (isRegistrationVerify || isPasswordResetComplete) {
      const raw = await upstream.text();
      const response = responseFromUpstream(upstream, raw, correlationId);
      if (upstream.ok) clearAuthChallengeCookie(response);
      return response;
    }
    if (isLogin || isRefresh) {
      const raw = await upstream.text();
      if (!upstream.ok) return responseFromUpstream(upstream, raw, correlationId);
      const tokens = JSON.parse(raw) as TokenResponse;
      const response = NextResponse.json(
        platform ? { platform_owner: tokens.platform_owner } : { user: tokens.user },
        { status: upstream.status },
      );
      setSessionCookies(response, tokens, platform);
      return response;
    }

    if (upstream.status === 401 && refreshToken) {
      try {
        const tokenBody = await runSingleFlightRefresh(request, correlationId, platform, refreshToken);
        upstream = await requestBackend(request, path, correlationId, tokenBody.access_token, requestBody);
        if (isFileResponse && upstream.ok) {
          const response = fileResponseFromUpstream(upstream, correlationId, isKnowledgePdf);
          setSessionCookies(response, tokenBody, platform);
          return response;
        }
        if (request.method === "GET" && path === "notifications/stream" && upstream.ok) {
          const response = eventStreamResponseFromUpstream(upstream, correlationId);
          setSessionCookies(response, tokenBody, platform);
          return response;
        }
        const raw = await upstream.text();
        const response = responseFromUpstream(upstream, raw, correlationId);
        setSessionCookies(response, tokenBody, platform);
        return response;
      } catch (error) {
        console.warn("session_refresh_failed", {
          correlation_id: correlationId,
          realm: platform ? "platform" : "tenant",
          method: request.method,
          route: path,
          error_type: error instanceof Error ? error.name : typeof error,
        });
      }
    }

    if (isFileResponse && upstream.ok) {
      return fileResponseFromUpstream(upstream, correlationId, isKnowledgePdf);
    }
    if (request.method === "GET" && path === "notifications/stream" && upstream.ok) {
      return eventStreamResponseFromUpstream(upstream, correlationId);
    }
    const raw = await upstream.text();
    const response = responseFromUpstream(upstream, raw, correlationId);
    if (upstream.status === 401) clearSessionCookies(response, platform);
    return response;
  } catch (error) {
    console.error(JSON.stringify({
      event: "backend_proxy_request_failed",
      correlation_id: correlationId,
      method: request.method,
      error_type: error instanceof Error ? error.name : "UnknownError",
    }));
    return localProblem(
      request,
      502,
      "Backend service is unavailable",
      "backend_unavailable",
      correlationId,
    );
  }
}

export const GET = forward;
export const HEAD = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
