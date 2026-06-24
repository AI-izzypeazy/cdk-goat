// Thin client for the Constructor Scout API with job polling.
// Set VITE_API_BASE_URL in your Lovable project (Project Settings -> env)
// to your deployed Python API, e.g. https://scout-api.onrender.com

import type { DeepResult, Job, RegionResult } from "@/types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function post(path: string, body: unknown): Promise<{ job_id: string }> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<{ job_id: string }>;
}

async function getJob<T>(jobId: string): Promise<Job<T>> {
  const res = await fetch(`${BASE}/api/job/${jobId}`);
  if (!res.ok) throw new Error(`job ${jobId} failed: ${res.status}`);
  return res.json() as Promise<Job<T>>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Kick off a job, then poll until it finishes. onStage reports progress. */
async function runJob<T>(
  start: () => Promise<{ job_id: string }>,
  onStage?: (stage: string) => void,
  { intervalMs = 1500, timeoutMs = 600_000 } = {},
): Promise<T> {
  const { job_id } = await start();
  const deadline = Date.now() + timeoutMs;
  let lastStage = "";
  while (Date.now() < deadline) {
    const job = await getJob<T>(job_id);
    if (job.stage && job.stage !== lastStage) {
      lastStage = job.stage;
      onStage?.(job.stage);
    }
    if (job.status === "done" && job.result) return job.result;
    if (job.status === "error") throw new Error(job.error ?? "scan failed");
    await sleep(intervalMs);
  }
  throw new Error("Timed out waiting for scan to finish.");
}

export async function checkHealth(): Promise<{ ok: boolean; llm: boolean }> {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error("API unreachable");
  return res.json();
}

export function scanRegion(
  params: { country: string; verticals?: string[]; per_vertical?: number; max_sites?: number; use_llm?: boolean },
  onStage?: (stage: string) => void,
): Promise<RegionResult> {
  return runJob<RegionResult>(() => post("/api/region", params), onStage);
}

export function deepScan(
  domain: string,
  onStage?: (stage: string) => void,
  use_llm = true,
): Promise<DeepResult> {
  return runJob<DeepResult>(() => post("/api/deep", { domain, use_llm }), onStage);
}

export function directScan(
  url: string,
  onStage?: (stage: string) => void,
  use_llm = true,
): Promise<DeepResult> {
  return runJob<DeepResult>(() => post("/api/scan", { url, use_llm }), onStage);
}

export { BASE as API_BASE };
