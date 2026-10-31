import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const ACCESS_COOKIE = "supportpilot_access";
const REFRESH_COOKIE = "supportpilot_refresh";
const REFRESH_MAX_AGE = 60 * 60 * 24 * 7;
const backendUrl = (process.env.BACKEND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: unknown;
};

function setSessionCookies(response: NextResponse, tokens: TokenResponse) {
  const secure = process.env.NODE_ENV === "production";
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: tokens.expires_in,
  });
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: REFRESH_MAX_AGE,
  });
}

function clearSessionCookies(response: NextResponse) {
  const common = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: 0,
  };
  response.cookies.set(ACCESS_COOKIE, "", common);
  response.cookies.set(REFRESH_COOKIE, "", common);
}

function isMutation(method: string) {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
}

function hasSameOrigin(request: NextRequest) {
  const expected = new URL(request.url).origin;
  const origin = request.headers.get("origin");
  if (origin) return origin === expected;
  const referer = request.headers.get("referer");
  return referer ? new URL(referer).origin === expected : false;
}

function responseFromUpstream(response: Response, body: string) {
  return new NextResponse(body || null, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}

async function requestBackend(
  request: NextRequest,
  path: string,
  accessToken?: string,
  body?: string,
  method = request.method,
) {
  const upstreamUrl = `${backendUrl}/api/v1/${path}${new URL(request.url).search}`;
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", "application/json");
  if (accessToken) headers.set("authorization", `Bearer ${accessToken}`);
  return fetch(upstreamUrl, {
    method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : body,
    cache: "no-store",
  });
}

async function forward(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  if (isMutation(request.method) && !hasSameOrigin(request)) {
    return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }
  const { path: segments } = await context.params;
  const path = segments.map(encodeURIComponent).join("/");
  const normalizedPath = `/${path}`;
  const isLogin = normalizedPath === "/auth/login" || normalizedPath === "/auth/register";
  const isAcceptInvite = normalizedPath === "/auth/invitations/accept";
  const isRefresh = normalizedPath === "/auth/refresh";
  const isLogout = normalizedPath === "/auth/logout";
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get(REFRESH_COOKIE)?.value;
  const accessToken = cookieStore.get(ACCESS_COOKIE)?.value;

  let requestBody: string | undefined;
  if (!["GET", "HEAD"].includes(request.method)) requestBody = await request.text();
  if (isRefresh || isLogout) {
    requestBody = JSON.stringify({ refresh_token: refreshToken ?? "" });
  }

  try {
    if (isLogout) {
      if (refreshToken) await requestBackend(request, path, undefined, requestBody);
      const response = NextResponse.json({ status: "signed_out" });
      clearSessionCookies(response);
      return response;
    }

    let upstream = await requestBackend(
      request,
      path,
      isLogin || isAcceptInvite || isRefresh ? undefined : accessToken,
      requestBody,
    );
    if (isLogin || isAcceptInvite || isRefresh) {
      const raw = await upstream.text();
      if (!upstream.ok) return responseFromUpstream(upstream, raw);
      const tokens = JSON.parse(raw) as TokenResponse;
      const response = NextResponse.json({ user: tokens.user }, { status: upstream.status });
      setSessionCookies(response, tokens);
      return response;
    }

    if (upstream.status === 401 && refreshToken) {
      const refreshResponse = await requestBackend(
        request,
        "auth/refresh",
        undefined,
        JSON.stringify({ refresh_token: refreshToken }),
        "POST",
      );
      if (refreshResponse.ok) {
        const tokenBody = (await refreshResponse.json()) as TokenResponse;
        upstream = await requestBackend(request, path, tokenBody.access_token, requestBody);
        const raw = await upstream.text();
        const response = responseFromUpstream(upstream, raw);
        setSessionCookies(response, tokenBody);
        return response;
      }
    }

    const raw = await upstream.text();
    const response = responseFromUpstream(upstream, raw);
    if (upstream.status === 401) clearSessionCookies(response);
    return response;
  } catch {
    return NextResponse.json({ detail: "Backend service is unavailable" }, { status: 502 });
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
