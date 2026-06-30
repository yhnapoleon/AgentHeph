// Mirror of the server SSE contract (agent_core/schemas/sse.py). The frontend ignores
// unknown event types so additive server changes never break it (contract rule).

export type EventType =
  | "meta"
  | "tool_call"
  | "tool_result"
  | "artifact"
  | "answer"
  | "error"
  | "done"
  | "write_proposal" // reserved (phase 2)
  | "proposal_status"; // reserved (phase 2)

export interface EventEnvelope {
  schema_version: string;
  event: EventType;
  run_id: string;
  thread_id: string;
  seq: number;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface ChatRequest {
  deployment_id: string;
  message: string;
  thread_id?: string;
  client_request_id?: string;
}
