import { NextRequest, NextResponse } from "next/server";

const backendUrl = (process.env.BACKEND_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, POST, OPTIONS",
  "access-control-allow-headers": "Authorization, Content-Type, Idempotency-Key",
  "access-control-max-age": "600",
  "cache-control": "no-store",
};

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: corsHeaders });
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward(request, context);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return forward(request, context);
}

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const safePath = path.map((part) => encodeURIComponent(part)).join("/");
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > 12_000) {
    return NextResponse.json({ detail: "Widget request is too large" }, { status: 413, headers: corsHeaders });
  }
  const headers = new Headers({ accept: "application/json" });
  for (const name of ["content-type", "authorization", "idempotency-key", "origin"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const requestBody = request.method === "POST" ? await request.text() : undefined;
    if (requestBody && new TextEncoder().encode(requestBody).byteLength > 12_000) {
      return NextResponse.json({ detail: "Widget request is too large" }, { status: 413, headers: corsHeaders });
    }
    const streaming = request.method === "GET" && path.at(-1) === "reply-stream";
    if (streaming) {
      headers.set("accept", "text/event-stream");
      headers.set("accept-encoding", "identity");
    }
    const response = await fetch(`${backendUrl}/api/v1/widget/${safePath}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: requestBody,
      cache: "no-store",
      signal: request.signal,
    });
    if (streaming && response.headers.get("content-type")?.startsWith("text/event-stream")) {
      return new NextResponse(response.body, {
        status: response.status,
        headers: {
          ...corsHeaders,
          "content-type": "text/event-stream",
          "cache-control": "no-store, no-transform",
          "x-accel-buffering": "no",
        },
      });
    }
    const responseBody = await response.arrayBuffer();
    return new NextResponse(responseBody, {
      status: response.status,
      headers: {
        ...corsHeaders,
        "content-type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "Support chat is temporarily unavailable" },
      { status: 502, headers: corsHeaders },
    );
  }
}
