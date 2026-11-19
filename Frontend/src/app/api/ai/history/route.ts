import { forward } from "@/lib/backend";

export const runtime = "nodejs";

export async function GET(request: Request) {
  const sessionId = new URL(request.url).searchParams.get("session_id");
  if (!sessionId || !/^[A-Za-z0-9_-]{1,200}$/.test(sessionId)) {
    return Response.json({ error: "Enter a session ID up to 200 characters." }, { status: 400 });
  }
  return forward(`ai/history?${new URLSearchParams({ session_id: sessionId })}`);
}
