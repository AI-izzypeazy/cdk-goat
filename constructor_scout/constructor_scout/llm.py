"""Claude-powered enrichment: concrete examples, summary and outreach copy.

Degrades gracefully to deterministic templates when no API key is available,
so the tool always produces a usable brief.
"""

from __future__ import annotations

import json

from .config import Config
from .knowledge import CAPABILITIES
from .models import Finding, Outreach, SiteProfile

SYSTEM_PROMPT = (
    "You are a senior solutions consultant for Constructor.io, an AI product "
    "discovery platform for retail/ecommerce (search, autosuggest, browse, "
    "recommendations, personalization, collections). You write crisp, concrete, "
    "non-hyperbolic sales material grounded ONLY in the evidence provided. "
    "Never invent metrics or facts not present in the input. Be specific to the "
    "site and avoid generic filler."
)


def _findings_payload(findings: list[Finding]) -> list[dict]:
    return [
        {
            "code": f.code,
            "title": f.title,
            "capability": f.capability,
            "severity": f.severity.value,
            "detail": f.detail,
            "evidence": f.evidence,
            "confidence": f.confidence,
        }
        for f in findings
    ]


class LLMEnricher:
    def __init__(self, config: Config):
        self.config = config
        self._client = None
        if config.llm_enabled:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=config.resolved_api_key())
            except Exception:
                self._client = None

    @property
    def active(self) -> bool:
        return self._client is not None

    # -- public API ---------------------------------------------------------
    def enrich(
        self, profile: SiteProfile, findings: list[Finding]
    ) -> tuple[str, Outreach]:
        """Return (summary, outreach). Also mutates findings[].example in place."""
        if not self.active or not findings:
            return self.template_brief(profile, findings)
        try:
            return self._enrich_llm(profile, findings)
        except Exception:
            return self.template_brief(profile, findings)

    # -- LLM path -----------------------------------------------------------
    def _enrich_llm(
        self, profile: SiteProfile, findings: list[Finding]
    ) -> tuple[str, Outreach]:
        payload = {
            "domain": profile.domain,
            "platform": profile.platform_name,
            "incumbent_vendor": profile.incumbent_vendor_name,
            "findings": _findings_payload(findings),
            "capabilities": {k: v.pitch for k, v in CAPABILITIES.items()},
        }
        instruction = (
            "Given this audit of a retail/ecommerce site, produce JSON with keys:\n"
            '  "examples": object mapping each finding "code" to a 1-2 sentence '
            "CONCRETE example a salesperson could demo (reference the specific "
            "behavior/query in the evidence; do not invent numbers).\n"
            '  "summary": 2-3 sentence executive summary of the discovery '
            "opportunity for this site.\n"
            '  "outreach_subject": a specific, non-spammy cold email subject line.\n'
            '  "outreach_body": a short (90-140 word) cold outreach email to the '
            "head of ecommerce/digital. Lead with the single most concrete observed "
            "gap, tie to revenue, reference the specific Constructor fix, end with a "
            "soft CTA offering a tailored demo. No fake metrics.\n"
            "Return ONLY valid JSON.\n\nAUDIT:\n"
            + json.dumps(payload, indent=2)
        )
        msg = self._client.messages.create(
            model=self.config.model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": instruction}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = _parse_json(text)
        examples = data.get("examples", {}) if isinstance(data, dict) else {}
        for f in findings:
            ex = examples.get(f.code)
            if ex:
                f.example = ex.strip()
        summary = (data.get("summary") or "").strip() if isinstance(data, dict) else ""
        outreach = Outreach(
            subject=(data.get("outreach_subject") or "").strip(),
            body=(data.get("outreach_body") or "").strip(),
        )
        if not summary or not outreach.subject:
            return self.template_brief(profile, findings)
        return summary, outreach

    # -- deterministic fallback --------------------------------------------
    def template_brief(
        self, profile: SiteProfile, findings: list[Finding]
    ) -> tuple[str, Outreach]:
        actionable = [f for f in findings if f.severity.value != "info"]
        for f in actionable:
            if not f.example and f.evidence:
                f.example = f"In testing we observed: {f.evidence[0]}."

        top = actionable[0] if actionable else None
        if profile.is_existing_constructor:
            summary = (
                f"{profile.domain} already runs Constructor.io — treat as an "
                "expansion account, not a new-logo prospect."
            )
            return summary, Outreach()

        gap_count = len(actionable)
        lead = top.title.lower() if top else "product-discovery gaps"
        summary = (
            f"{profile.domain} ({profile.platform_name}) shows {gap_count} "
            f"addressable product-discovery gap(s), led by {lead}. "
            f"Incumbent discovery: {profile.incumbent_vendor_name}. "
            "Strong fit for a tailored Constructor.io walkthrough."
        )
        subject = (
            f"Quick observation about search & discovery on {profile.domain}"
        )
        body_lines = [
            "Hi there,",
            "",
            f"I took a look at {profile.domain} from a shopper's perspective and "
            "noticed a few product-discovery gaps that tend to cost retailers "
            "revenue:",
            "",
        ]
        for f in actionable[:3]:
            body_lines.append(f"• {f.title} — {f.recommendation}")
        body_lines += [
            "",
            "Constructor.io is AI product discovery (search, autosuggest, browse, "
            "recommendations, personalization) optimized for revenue. I'd be happy "
            "to put together a short, tailored walkthrough using your own site.",
            "",
            "Worth a 20-minute look?",
            "",
            "Best regards,",
        ]
        return summary, Outreach(subject=subject, body="\n".join(body_lines))


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except Exception:
        return {}
