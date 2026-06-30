// POST /chat returns text/event-stream. EventSource is GET-only, so we read the body
// stream and parse `data:` frames ourselves, yielding one EventEnvelope per frame.
import type { ChatRequest, EventEnvelope } from "./contract";

export async function* streamChat(
  req: ChatRequest,
  opts: { baseUrl?: string; headers?: Record<string, string> } = {},
): AsyncGenerator<EventEnvelope> {
  const resp = await fetch(`${opts.baseUrl ?? ""}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(opts.headers ?? {}) },
    body: JSON.stringify(req),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`chat failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (line) yield JSON.parse(line.slice("data: ".length)) as EventEnvelope;
    }
  }
}
