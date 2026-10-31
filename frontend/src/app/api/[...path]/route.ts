import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const TENANT_ACCESS_COOKIE = "supportpilot_access";
const TENANT_REFRESH_COOKIE = "supportpilot_refresh";
const PLATFORM_ACCESS_COOKIE = "supportpilot_platform_access";
const PLATFORM_REFRESH_COOKIE = "supportpilot_platform_refresh";
const REFRESH_MAX_AGE = 60 * 60 * 24 * 7;
const backendUrl = (process.env.BACKEND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user?: unknown;
  platform_owner?: unknown;
};

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

function responseFromUpstream(response: Response, body: string) {
  const headers = new Headers({
    "content-type": response.headers.get("content-type") ?? "application/json",
    "cache-control": "no-store",
  });
  const location = response.headers.get("location");
  if (location) headers.set("location", location);
  return new NextResponse(body || null, {
    status: response.status,
    headers,
  });
}

function localProblem(request: NextRequest, status: number, detail: string, code: string) {
  const title = status === 403 ? "Forbidden" : status === 413 ? "Content Too Large" : "Bad Gateway";
  const problem = {
    type: `urn:supportpilot:problem:${code}`,
    title,
    status,
    detail,
    instance: new URL(request.url).pathname,
    code,
  };
  return new NextResponse(JSON.stringify(problem), {
    status,
    headers: { "content-type": "application/problem+json", "cache-control": "no-store" },
  });
}

async function requestBackend(
  request: NextRequest,
  path: string,
  accessToken?: string,
  body?: BodyInit,
  method = request.method,
) {
  const isHealthCheck = path === "health/ready" || path === "health/live";
  const upstreamPath = isHealthCheck ? `/${path}` : `/api/v1/${path}`;
  const upstreamUrl = `${backendUrl}${upstreamPath}${new URL(request.url).search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  else if (body && !["GET", "HEAD"].includes(method)) headers.set("content-type", "application/json");
  headers.set("accept", "application/json");
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
  if (isMutation(request.method) && !hasSameOrigin(request)) {
    return localProblem(request, 403, "Cross-origin request rejected", "cross_origin_rejected");
  }
  const { path: segments } = await context.params;
  const path = segments.map(encodeURIComponent).join("/");
  const normalizedPath = `/${path}`;
  const platform = normalizedPath.startsWith("/platform/");
  const isTenantLogin = normalizedPath === "/auth/login";
  const isTenantRegister = normalizedPath === "/auth/register";
  const isAcceptInvite = normalizedPath === "/auth/invitations/accept";
  const isTenantRefresh = normalizedPath === "/auth/refresh";
  const isTenantLogout = normalizedPath === "/auth/logout";
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

  let requestBody: BodyInit | undefined;
  if (!["GET", "HEAD"].includes(request.method)) {
    const contentType = request.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      requestBody = await request.text();
    } else {
      const declaredLength = Number(request.headers.get("content-length") ?? 0);
      if (declaredLength > 20 * 1024 * 1024) {
        return localProblem(request, 413, "Document exceeds the 20 MB upload limit", "upload_too_large");
      }
      const binaryBody = await request.arrayBuffer();
      if (binaryBody.byteLength > 20 * 1024 * 1024) {
        return localProblem(request, 413, "Document exceeds the 20 MB upload limit", "upload_too_large");
      }
      requestBody = binaryBody;
    }
  }
  if (isRefresh || isLogout) {
    requestBody = JSON.stringify({ refresh_token: refreshToken ?? "" });
  }

  try {
    if (isLogout) {
      if (refreshToken) await requestBackend(request, path, undefined, requestBody);
      const response = NextResponse.json({ status: "signed_out" });
      clearSessionCookies(response, platform);
      return response;
    }

    let upstream = await requestBackend(
      request,
      path,
      isLogin || isRefresh || isTenantRegister || isAcceptInvite ? undefined : accessToken,
      requestBody,
    );
    if (isTenantRegister) {
      const raw = await upstream.text();
      const response = responseFromUpstream(upstream, raw);
      if (upstream.ok) clearSessionCookies(response, false);
      return response;
    }
    if (isLogin || isAcceptInvite || isRefresh) {
      const raw = await upstream.text();
      if (!upstream.ok) return responseFromUpstream(upstream, raw);
      const tokens = JSON.parse(raw) as TokenResponse;
      const response = NextResponse.json(
        platform ? { platform_owner: tokens.platform_owner } : { user: tokens.user },
        { status: upstream.status },
      );
      setSessionCookies(response, tokens, platform);
      return response;
    }

    if (upstream.status === 401 && refreshToken) {
      const refreshPath = platform ? "platform/auth/refresh" : "auth/refresh";
      const refreshResponse = await requestBackend(
        request,
        refreshPath,
        undefined,
        JSON.stringify({ refresh_token: refreshToken }),
        "POST",
      );
      if (refreshResponse.ok) {
        const tokenBody = (await refreshResponse.json()) as TokenResponse;
        upstream = await requestBackend(request, path, tokenBody.access_token, requestBody);
        const raw = await upstream.text();
        const response = responseFromUpstream(upstream, raw);
        setSessionCookies(response, tokenBody, platform);
        return response;
      }
    }

    const raw = await upstream.text();
    const response = responseFromUpstream(upstream, raw);
    if (upstream.status === 401) clearSessionCookies(response, platform);
    return response;
  } catch {
    return localProblem(request, 502, "Backend service is unavailable", "backend_unavailable");
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
