// Shared API types, mirrored from backend Pydantic schemas.

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
}