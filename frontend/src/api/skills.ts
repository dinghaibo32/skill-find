import type { SkillsResponse } from "../types/skill";
import { getJson, postJson } from "./http";

function sessionQuery(sessionId?: string): string {
  return sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
}

export function fetchSkills(sessionId?: string): Promise<SkillsResponse> {
  return getJson(`/api/skills${sessionQuery(sessionId)}`);
}

export function rescanSkills(sessionId?: string): Promise<SkillsResponse> {
  return postJson(`/api/skills/rescan${sessionQuery(sessionId)}`);
}

export function setSimulate(enabled: boolean, sessionId?: string): Promise<SkillsResponse> {
  return postJson(`/api/debug/simulate${sessionQuery(sessionId)}`, { enabled });
}
