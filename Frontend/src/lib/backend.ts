import "server-only";

const TIMEOUT_MS = 180_000;
const NO_STORE = { "Cache-Control": "no-store" } as const;

function fail(error: string, status: number): Response {
  return Response.json({ error }, { status, headers: NO_STORE });
}

function resolveBase(): URL | null {
  const configured = process.env.BACKEND_URL || "http://localhost:8000";
  try {
    const url = new URL(configured.endsWith("/") ? configured : `${configured}/`);
    return ["http:", "https:"].includes(url.protocol) ? url : null;
  } catch {
    return null;
  }
}

function buildUrl(path: string, base: URL): URL | null {
  try {
    // Leading slashes hata do taake base ka path bhi preserve rahe
    const url = new URL(path.replace(/^\/+/, ""), base);
    // Absolute URL ya traversal se kisi aur host/path pe jaana block
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)) return null;
    return url;
  } catch {
    return null;
  }
}

function buildHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);

  // Hop-by-hop / sensitive headers jo backend ko forward nahi hone chahiye
  for (const name of ["host", "cookie", "content-length", "connection", "transfer-encoding"]) {
    headers.delete(name);
  }

  headers.set("Accept", "application/json");

  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  // API key hamesha server se aaye, caller se nahi
  // Both names are accepted by the backend; prefer its canonical name.
  const apiKey = process.env.AUTHENTICATED_KEY || process.env.SECRET_KEY;
  if (apiKey) headers.set("X-API-KEY", apiKey);
  else headers.delete("X-API-KEY");

  return headers;
}

export async function forward(path: string, init?: RequestInit): Promise<Response> {
  const base = resolveBase();
  if (!base) {
    return fail("The assistant service URL is not configured correctly.", 503);
  }

  const url = buildUrl(path, base);
  if (!url) {
    return fail("Invalid request path.", 400);
  }

  const timeout = AbortSignal.timeout(TIMEOUT_MS);
  const signal = init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout;

  try {
    const response = await fetch(url, {
      ...init,
      headers: buildHeaders(init),
      signal,
      cache: "no-store",
      redirect: "error",
    });

    if (!response.ok) {
      // Record upstream diagnostics server-side, without returning them to users.
      const upstreamBody = await response.text().catch(() => "");
      console.error(`[forward] backend ${response.status} for ${url.pathname}: ${upstreamBody.slice(0, 2000)}`);

      if (response.status === 429) {
        return fail("The assistant is busy. Please wait a moment, then reload history.", 429);
      }
      if (response.status === 404) {
        const isOrderLookup = /\/order\/[^/]+$/.test(url.pathname);
        return fail(
          isOrderLookup ? "That order could not be found. Check the order ID and try again." : "The requested assistant resource could not be found.",
          404,
        );
      }
      if (response.status === 401 || response.status === 403) {
        return fail("The assistant service rejected its server credentials. Check that the frontend server key matches AUTHENTICATED_KEY in Backend/.env, then restart both services.", 502);
      }
      const status = response.status >= 500 ? 502 : response.status;
      return fail("The assistant couldn't complete this request. Reload history before sending again.", status);
    }

    if (response.status === 204) {
      return new Response(null, { status: 204, headers: NO_STORE });
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      console.error(`[forward] non-JSON response for ${url.pathname}`);
      return fail("The assistant returned an unexpected response. Reload history and try again.", 502);
    }

    return Response.json(body, { headers: NO_STORE });
  } catch (error) {
    const name = error instanceof Error ? error.name : "";

    if (name === "TimeoutError") {
      return fail(
        "The assistant took longer than expected. Your message may still be processing. Wait a moment and reload history.",
        504,
      );
    }
    if (name === "AbortError") {
      return fail("The request was cancelled.", 499);
    }

    console.error("[forward] fetch failed:", error);
    return fail("We couldn't connect to the assistant service. Make sure FastAPI is running and reload history.", 503);
  }
}
