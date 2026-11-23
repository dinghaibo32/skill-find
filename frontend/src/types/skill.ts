// Types mirroring backend skill-system schemas.

export interface SkillInfo {
  name: string;
  description: string;
  source_dir: string;
  status: "active" | "overridden";
  overridden_by: string | null;
  tokens: number;
  loaded: boolean;
}

export interface InjectionInfo {
  tokens: number;
  budget: number;
  strategy: "full" | "truncated" | "names_only";
  skill_count: number;
}

export interface ScanIssue {
  path: string;
  reason: string;
}

export interface SkillsResponse {
  skills: SkillInfo[];
  injection: InjectionInfo;
  issues: ScanIssue[];
  simulating: boolean;
}

export interface AgentEvent {
  type: "load_skill" | "read_skill_file";
  skill: string;
  path: string | null;
  ok: boolean;
  error: string | null;
}

export interface LLMUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost: number;
}

export interface AgentChatResponse {
  reply: string;
  events: AgentEvent[];
  usage: LLMUsage;
  injection_tokens: number;
  tool_rounds: number;
}

export interface EvalActual {
  action: string;
  skill: string | null;
}

export interface EvalRow {
  id: number;
  query: string;
  category: string;
  expected_skill: string | null;
  actual: EvalActual | null;
  passed: boolean;
  error: string | null;
}

export interface EvalSummary {
  total: number;
  passed: number;
  accuracy: number;
  by_category: Record<string, { total: number; passed: number }>;
}

export interface EvalReport {
  results: EvalRow[];
  summary: EvalSummary;
}
