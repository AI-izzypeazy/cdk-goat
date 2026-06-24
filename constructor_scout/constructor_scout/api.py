"""HTTP API around Constructor Scout, for the Lovable (or any) web UI.

Long-running scans are dispatched as background jobs; the UI polls
GET /api/job/{id} until status == "done".

Run it:
    pip install "constructor-scout[api]"      # or: pip install fastapi uvicorn
    export ANTHROPIC_API_KEY=sk-ant-...        # optional, for tailored copy
    uvicorn constructor_scout.api:app --reload --port 8000

Endpoints:
    POST /api/region  {country, verticals?, per_vertical?, max_sites?}  -> {job_id}
    POST /api/deep    {domain}                                          -> {job_id}
    POST /api/scan    {url}                                             -> {job_id}
    GET  /api/job/{id}                                                  -> job state
    GET  /health
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "FastAPI is required for the API. Install with: "
        'pip install "constructor-scout[api]"  (or pip install fastapi uvicorn)'
    ) from exc

from .config import Config
from .discovery import discover_many
from .knowledge import CAPABILITIES
from .models import Finding, SiteReport, Severity
from .pipeline import scan_many, scan_site
from .regions import region_queries
from .reporting import (
    actionable_findings,
    rank_by_discrepancies,
    render_problem_solution,
)

app = FastAPI(title="Constructor Scout API", version="0.1.0")

# Lovable preview/published apps live on lovable.app / lovableproject.com domains.
# Lock CORS_ORIGINS down to your own published URL in production if you prefer.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------- #
# in-memory job store (single-process; fine for self-host / demo)
# --------------------------------------------------------------------------- #
_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _new_job(kind: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "kind": kind, "status": "queued",
                         "stage": "queued", "result": None, "error": None}
    return job_id


def _set(job_id: str, **fields) -> None:
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def _run(job_id: str, fn) -> None:
    def worker():
        _set(job_id, status="running")
        try:
            _set(job_id, status="done", stage="done", result=fn(lambda s: _set(job_id, stage=s)))
        except Exception as exc:  # surface message to the UI
            _set(job_id, status="error", error=str(exc))
    threading.Thread(target=worker, daemon=True).start()


# --------------------------------------------------------------------------- #
# serialization
# --------------------------------------------------------------------------- #
def _finding_dict(f: Finding) -> dict[str, Any]:
    cap = CAPABILITIES.get(f.capability)
    return {
        "code": f.code,
        "title": f.title,
        "severity": f.severity.value,
        "confidence": f.confidence,
        "capability": cap.name if cap else f.capability,
        "capability_docs": cap.docs if cap else None,
        # framed as the UI presents it:
        "problem": f.detail,
        "example": f.example or None,
        "solution": f.recommendation,
        "evidence": f.evidence,
    }


def _shortlist_row(rank: int, r: SiteReport) -> dict[str, Any]:
    gaps = actionable_findings(r)
    top = sorted(gaps, key=lambda f: list(Severity).index(f.severity))
    return {
        "rank": rank,
        "domain": r.domain,
        "gaps": len(gaps),
        "opportunity": round(r.opportunity_score),
        "fit": round(r.fit_score),
        "platform": r.profile.platform_name,
        "incumbent": r.profile.incumbent_vendor_name,
        "priority": r.priority,
        "existing_customer": r.priority == "EXISTING",
        "top_gap": top[0].title if top else None,
    }


def _deep_dict(r: SiteReport) -> dict[str, Any]:
    gaps = sorted(actionable_findings(r), key=lambda f: list(Severity).index(f.severity))
    return {
        "domain": r.domain,
        "platform": r.profile.platform_name,
        "incumbent": r.profile.incumbent_vendor_name,
        "priority": r.priority,
        "opportunity": round(r.opportunity_score),
        "fit": round(r.fit_score),
        "summary": r.summary,
        "findings": [_finding_dict(f) for f in gaps],
        "outreach": {"subject": r.outreach.subject, "body": r.outreach.body},
        "markdown": render_problem_solution(r),
        "notes": r.notes,
    }


def _config(use_llm: bool = True) -> Config:
    # robots respected, gentle defaults; tune via env if self-hosting.
    return Config(respect_robots=True, delay=1.0, use_llm=use_llm)


# --------------------------------------------------------------------------- #
# request models
# --------------------------------------------------------------------------- #
class RegionReq(BaseModel):
    country: str
    verticals: Optional[list[str]] = None
    per_vertical: int = 5
    max_sites: int = 20
    use_llm: bool = True


class DeepReq(BaseModel):
    domain: str
    use_llm: bool = True


class ScanReq(BaseModel):
    url: str
    use_llm: bool = True


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, Any]:
    cfg = _config()
    return {"ok": True, "llm": bool(cfg.resolved_api_key())}


@app.post("/api/region")
def start_region(req: RegionReq) -> dict[str, str]:
    job_id = _new_job("region")

    def task(stage):
        cfg = _config(req.use_llm)
        stage("discovering")
        queries = region_queries(req.country, req.verticals)
        domains = discover_many(queries, req.per_vertical, cfg)[: req.max_sites]
        if not domains:
            raise RuntimeError(
                "No sites discovered. The server needs open outbound internet; "
                "try a broader country or use /api/scan with a known URL."
            )
        stage(f"scanning {len(domains)} sites")
        reports = scan_many(domains, cfg, depth="shallow")
        ranked = rank_by_discrepancies(reports)
        return {
            "country": req.country,
            "scanned": len(reports),
            "shortlist": [_shortlist_row(i, r) for i, r in enumerate(ranked, 1)],
        }

    _run(job_id, task)
    return {"job_id": job_id}


@app.post("/api/deep")
def start_deep(req: DeepReq) -> dict[str, str]:
    job_id = _new_job("deep")

    def task(stage):
        cfg = _config(req.use_llm)
        stage("deep scanning")
        report = scan_site(req.domain, cfg, depth="deep")
        return _deep_dict(report)

    _run(job_id, task)
    return {"job_id": job_id}


@app.post("/api/scan")
def start_scan(req: ScanReq) -> dict[str, str]:
    job_id = _new_job("scan")

    def task(stage):
        cfg = _config(req.use_llm)
        stage("scanning")
        report = scan_site(req.url, cfg, depth="deep")
        return _deep_dict(report)

    _run(job_id, task)
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return dict(job)
