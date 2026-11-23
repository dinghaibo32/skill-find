import type { EvalReport } from "../types/skill";
import { getJson, postJson } from "./http";

export function runEvals(): Promise<EvalReport> {
  return postJson("/api/evals/run");
}

export function fetchEvalResults(): Promise<EvalReport> {
  return getJson("/api/evals/results");
}
