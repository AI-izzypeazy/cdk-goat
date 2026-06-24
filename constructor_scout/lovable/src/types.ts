// Shared types mirroring the Constructor Scout API (constructor_scout/api.py).

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type JobStatus = "queued" | "running" | "done" | "error";

export interface ShortlistRow {
  rank: number;
  domain: string;
  gaps: number;
  opportunity: number;
  fit: number;
  platform: string;
  incumbent: string;
  priority: string;
  existing_customer: boolean;
  top_gap: string | null;
}

export interface RegionResult {
  country: string;
  scanned: number;
  shortlist: ShortlistRow[];
}

export interface Finding {
  code: string;
  title: string;
  severity: Severity;
  confidence: number;
  capability: string;
  capability_docs: string | null;
  problem: string;
  example: string | null;
  solution: string;
  evidence: string[];
}

export interface DeepResult {
  domain: string;
  platform: string;
  incumbent: string;
  priority: string;
  opportunity: number;
  fit: number;
  summary: string;
  findings: Finding[];
  outreach: { subject: string; body: string };
  markdown: string;
  notes: string[];
}

export interface Job<T> {
  id: string;
  kind: "region" | "deep" | "scan";
  status: JobStatus;
  stage: string;
  result: T | null;
  error: string | null;
}
