import { NextRequest, NextResponse } from "next/server";

const ALLOWED = new Set([
  "health",
  "positions",
  "analysis",
  "status-reino",
  "missoes-ativas",
  "analise-risco",
  "transacao-nao-assinada",
  "previsoes",
]);

function backendBase(): string {
  return (process.env.BACKEND_URL || "http://127.0.0.1:8091").replace(/\/$/, "");
}

async function proxy(request: NextRequest, path: string[]) {
  const root = path[0];
  if (!root || !ALLOWED.has(root)) {
    return NextResponse.json({ detail: "Caminho não permitido." }, { status: 404 });
  }

  const target = new URL(`${backendBase()}/${path.map(encodeURIComponent).join("/")}`);
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    const body = await request.text();
    if (body.length > 100_000) {
      return NextResponse.json({ detail: "Pedido grande demais." }, { status: 413 });
    }
    init.body = body;
  }

  try {
    const response = await fetch(target, init);
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "A API da carteira não respondeu neste host." },
      { status: 503 },
    );
  }
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function DELETE(request: NextRequest, context: Context) {
  return proxy(request, (await context.params).path);
}
