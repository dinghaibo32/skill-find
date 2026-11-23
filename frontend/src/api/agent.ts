import type { AgentChatResponse } from "../types/skill";
import { postJson } from "./http";

export function sendChat(sessionId: string, message: string): Promise<AgentChatResponse> {
  return postJson("/api/agent/chat", { session_id: sessionId, message });
}
