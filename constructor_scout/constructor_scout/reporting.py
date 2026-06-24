"""Write per-site JSON + Markdown briefs and a cross-site leaderboard."""

from __future__ import annotations

import csv
import datetime as _dt
import json
import os
import re

from .knowledge import CAPABILITIES
from .models import Severity, SiteReport

SEV_ORDER = {s: i for i, s in enumerate(
    [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]
)}
SEV_EMOJI = {
    Severity.CRITICAL: "🔴", Severity.HIGH: "🟠", Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵", Severity.INFO: "⚪",
}


def _slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")


def _ts(epoch: float) -> str:
    return _dt.datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d %H:%M UTC")


def write_site_report(report: SiteReport, out_dir: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    slug = _slug(report.domain)
    json_path = os.path.join(out_dir, f"{slug}.json")
    md_path = os.path.join(out_dir, f"{slug}.brief.md")

    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=2)

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(render_brief(report))

    return {"json": json_path, "brief": md_path}


def render_brief(report: SiteReport) -> str:
    p = report.profile
    findings = sorted(report.findings, key=lambda f: (SEV_ORDER[f.severity], -f.confidence))
    actionable = [f for f in findings if f.severity != Severity.INFO]

    lines: list[str] = []
    lines.append(f"# Constructor.io Prospect Brief — {report.domain}")
    lines.append("")
    lines.append(f"_Generated {_ts(report.generated_at)} · Constructor Scout_")
    lines.append("")
    lines.append("## Snapshot")
    lines.append("")
    lines.append(f"| | |")
    lines.append(f"|---|---|")
    lines.append(f"| **Priority** | **{report.priority}** |")
    lines.append(f"| Fit score | {report.fit_score:.0f} / 100 |")
    lines.append(f"| Opportunity score | {report.opportunity_score:.0f} / 100 |")
    lines.append(f"| Platform | {p.platform_name} |")
    lines.append(f"| Incumbent discovery | {p.incumbent_vendor_name} |")
    lines.append(f"| Site search found | {'yes' if p.has_search else 'no'} |")
    lines.append(f"| Pages crawled | {report.pages_crawled} |")
    lines.append("")
    if report.summary:
        lines.append("## Executive summary")
        lines.append("")
        lines.append(report.summary)
        lines.append("")

    lines.append("## Findings & fixes")
    lines.append("")
    if not actionable:
        lines.append("_No actionable discovery gaps detected._")
        lines.append("")
    for i, f in enumerate(actionable, 1):
        cap = CAPABILITIES.get(f.capability)
        lines.append(f"### {i}. {SEV_EMOJI[f.severity]} {f.title}")
        lines.append("")
        lines.append(f"- **Severity:** {f.severity.value} · **Confidence:** {f.confidence:.0%}")
        if cap:
            lines.append(f"- **Constructor capability:** {cap.name}")
        lines.append(f"- **What we saw:** {f.detail}")
        if f.example:
            lines.append(f"- **Concrete example:** {f.example}")
        lines.append(f"- **Fix:** {f.recommendation}")
        if f.evidence:
            lines.append(f"- **Evidence:** {'; '.join(f.evidence)}")
        lines.append("")

    # Informational / positioning notes
    info = [f for f in findings if f.severity == Severity.INFO]
    if info:
        lines.append("## Positioning notes")
        lines.append("")
        for f in info:
            lines.append(f"- **{f.title}** — {f.recommendation}")
        lines.append("")

    if report.outreach.subject or report.outreach.body:
        lines.append("## Draft outreach")
        lines.append("")
        if report.outreach.subject:
            lines.append(f"**Subject:** {report.outreach.subject}")
            lines.append("")
        if report.outreach.body:
            lines.append("```")
            lines.append(report.outreach.body)
            lines.append("```")
        lines.append("")

    lines.append("---")
    lines.append(
        "_Heuristic audit from public pages; verify findings before outreach. "
        "Constructor Scout is a prospecting aid, not a definitive technical assessment._"
    )
    lines.append("")
    return "\n".join(lines)


def write_leaderboard(reports: list[SiteReport], out_dir: str) -> dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    ranked = sorted(
        reports,
        key=lambda r: (r.priority == "EXISTING", -(0.45 * r.fit_score + 0.55 * r.opportunity_score)),
    )
    csv_path = os.path.join(out_dir, "leaderboard.csv")
    md_path = os.path.join(out_dir, "leaderboard.md")

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "domain", "priority", "fit", "opportunity", "platform",
            "incumbent_vendor", "actionable_findings", "top_gap",
        ])
        for r in ranked:
            actionable = [f for f in r.findings if f.severity != Severity.INFO]
            top = sorted(actionable, key=lambda f: SEV_ORDER[f.severity])
            w.writerow([
                r.domain, r.priority, f"{r.fit_score:.0f}", f"{r.opportunity_score:.0f}",
                r.profile.platform_name, r.profile.incumbent_vendor_name,
                len(actionable), top[0].title if top else "",
            ])

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(f"# Constructor Scout — Prospect Leaderboard\n\n")
        fh.write(f"_Generated {_ts(reports[0].generated_at) if reports else ''} · {len(reports)} sites scanned_\n\n")
        fh.write("| Rank | Domain | Priority | Fit | Opp | Platform | Incumbent | Gaps | Top gap |\n")
        fh.write("|---|---|---|---|---|---|---|---|---|\n")
        for i, r in enumerate(ranked, 1):
            actionable = [f for f in r.findings if f.severity != Severity.INFO]
            top = sorted(actionable, key=lambda f: SEV_ORDER[f.severity])
            fh.write(
                f"| {i} | {r.domain} | {r.priority} | {r.fit_score:.0f} | "
                f"{r.opportunity_score:.0f} | {r.profile.platform_name} | "
                f"{r.profile.incumbent_vendor_name} | {len(actionable)} | "
                f"{top[0].title if top else '—'} |\n"
            )
        fh.write("\n_Priority A = best fit + most opportunity. EXISTING = already a Constructor customer._\n")

    return {"csv": csv_path, "md": md_path}
