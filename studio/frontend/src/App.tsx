// The single SSE renderer reused by every bot: it renders the contract event stream
// (tool calls, the final answer, errors), not any per-app UI. Deliberately minimal —
// styling/components are out of scope for the M1 scaffold.
import { useState } from "react";
import type { EventEnvelope } from "./contract";
import { streamChat } from "./sseClient";

const DEPLOYMENT_ID = "demo";

export default function App() {
  const [message, setMessage] = useState("which tickets are open?");
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [threadId, setThreadId] = useState<string | undefined>();

  async function send() {
    setBusy(true);
    setEvents([]);
    setAnswer("");
    try {
      for await (const ev of streamChat(
        { deployment_id: DEPLOYMENT_ID, message, thread_id: threadId },
        // dev auth: replace with real auth headers in production.
        { headers: { "X-Subject": "alice", "X-Roles": "member" } },
      )) {
        setEvents((prev) => [...prev, ev]);
        if (ev.event === "meta") setThreadId(ev.thread_id);
        if (ev.event === "answer") setAnswer(String(ev.data.text ?? ""));
        if (ev.event === "error") setAnswer(`Error: ${String(ev.data.message ?? "")}`);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 720, margin: "2rem auto" }}>
      <h1>AgentHeph chat</h1>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          style={{ flex: 1 }}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !busy && send()}
        />
        <button onClick={send} disabled={busy}>
          {busy ? "…" : "Send"}
        </button>
      </div>

      {answer && (
        <section style={{ marginTop: 16 }}>
          <h2>Answer</h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{answer}</p>
        </section>
      )}

      <section style={{ marginTop: 16, color: "#666" }}>
        <h3>Event trace</h3>
        <ol>
          {events
            .filter((e) => e.event === "tool_call" || e.event === "tool_result")
            .map((e) => (
              <li key={`${e.seq}`}>
                <code>{e.event}</code> {String(e.data.tool ?? "")}{" "}
                <small>({String(e.data.call_id ?? "")})</small>
              </li>
            ))}
        </ol>
      </section>
    </main>
  );
}
