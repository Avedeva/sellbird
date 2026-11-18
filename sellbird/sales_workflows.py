"""Local AI workflows and transparent product-specific prospect scoring."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import Field

from sellbird.local_ai import LocalAIError, OllamaService
from sellbird.sales_schemas import (
    BusinessProfile, BuyingSignalResult, GeneratedEmail, ICPProfile,
    ProblemStatement, ReplyClassification,
    StrictModel,
)
from sellbird.sales_store import SalesStore


class WorkflowInputError(ValueError):
    """A workflow has missing or inconsistent persisted context."""


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]{3,}", (text or "").lower())
            if word not in {"the", "and", "for", "with", "that", "this", "from", "their", "your"}}


def _json_context(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _matching(text: str, candidates: list[str]) -> int:
    body = _words(text)
    vocab = set().union(*(_words(candidate) for candidate in candidates)) if candidates else set()
    if not body or not vocab:
        return 50 if not candidates else 0
    overlap = len(body & vocab)
    return min(100, round(100 * overlap / max(1, min(len(vocab), 8))))


class SalesWorkflows:
    def __init__(self, store: SalesStore, ai: OllamaService):
        self.store, self.ai = store, ai

    async def company(self, company_id: str) -> dict:
        company = await self.store.get_company(company_id)
        if not company:
            raise WorkflowInputError("Company was not found")
        return company

    async def product(self, product_id: str, company_id: str | None = None) -> tuple[dict, dict]:
        product = await self.store.get_product(product_id)
        if not product:
            raise WorkflowInputError("Product was not found")
        if company_id and product["company_id"] != company_id:
            raise WorkflowInputError("Product does not belong to the selected company")
        company = await self.company(product["company_id"])
        return company, product

    async def prospect(self, product_id: str, prospect_id: str) -> tuple[dict, dict, dict, list[dict]]:
        company, product = await self.product(product_id)
        prospect = await self.store.get_prospect(prospect_id)
        if not prospect or prospect["company_id"] != company["id"]:
            raise WorkflowInputError("Prospect does not belong to this company and product context")
        sources = await self.store.research_sources(prospect_id)
        return company, product, prospect, sources

    async def generate_profile(self, company_id: str) -> dict:
        company = await self.company(company_id)
        result = await self.ai.generate_json(
            "business_profile",
            "Create a concise structured business profile from this locally stored seller information. "
            "Do not add facts that are not present; list gaps in missing_information.\n\n" + _json_context(company),
            BusinessProfile,
        )
        profile = result.model_dump()
        await self.store.save_profile(company_id, profile)
        return profile

    async def generate_icp(self, product_id: str) -> dict:
        company, product = await self.product(product_id)
        payload = {"seller_company": company, "selected_product": product}
        result = await self.ai.generate_json(
            "product_icp",
            "Generate an ideal customer profile for the selected product. Every criterion must relate to "
            "this product's features, benefits, target market, pains, and sales position. Do not transfer "
            "criteria from another product. Leave unknown ranges blank and label assumptions in qualification criteria.\n\n"
            + _json_context(payload), ICPProfile,
        )
        icp = result.model_dump()
        await self.store.save_icp(product_id, icp)
        await self.store.save_artifact(product_id, None, "icp", icp)
        return icp

    async def summarize_research(self, product_id: str, prospect_id: str) -> dict:
        company, product, prospect, sources = await self.prospect(product_id, prospect_id)
        evidence = [{"url": row["url"], "fetched_at": row["fetched_at"],
                     "title": row["title"], "text": row["extracted_text"][:12000]}
                    for row in sources]
        result = await self.ai.generate_json(
            "prospect_research_summary",
            "Summarize only the supplied cached public research and prospect record for the selected product. "
            "Each factual finding must name its source URL, include an exact evidence excerpt copied from that URL, "
            "and set evidence_type to verified, extracted, or inferred. The excerpt must be exact. If cached evidence "
            "is absent or weak, return no findings and set insufficient_evidence=true.\n\n" +
            _json_context({"product": product, "prospect": prospect, "cached_sources": evidence}),
            ResearchSummary,
        )
        content = result.model_dump()
        source_text = {row["url"]: row["extracted_text"] for row in sources}
        for finding in content["findings"]:
            source = source_text.get(finding["source_url"])
            if source is None or not _contains_quote(source, finding["evidence_excerpt"]):
                raise LocalAIError("Research summary included a finding without an exact cached-source excerpt")
        await self.store.save_artifact(product_id, prospect_id, "research_summary", content,
                                       [item["source_url"] for item in content.get("findings", []) if item.get("source_url")])
        return content

    async def classify_signals(self, product_id: str, prospect_id: str) -> dict:
        company, product, prospect, sources = await self.prospect(product_id, prospect_id)
        eligible_source_text = {row["url"]: row["extracted_text"] for row in sources if row["status"] == "ok"}
        payload = {"product": product, "prospect": prospect,
                   "cached_sources": [{"url": row["url"], "fetched_at": row["fetched_at"],
                                       "status": row["status"],
                                       "text": row["extracted_text"][:12000]} for row in sources]}
        result = await self.ai.generate_json(
            "buying_signal_classification",
            "Identify only buying signals directly supported by cached sources whose status is exactly 'ok'. "
            "Treat demo, failed, or otherwise non-ok sources as unverified examples and never use them as signals. "
            "For each signal, "
            "copy a short exact supporting excerpt, use its exact URL, and explain product relevance as a hypothesis. "
            "Do not infer funding, hiring, expansion, launches, adoption, or leadership changes from generic text. "
            "Return insufficient_evidence=true and an empty signals list when no eligible source supports a signal.\n\n"
            + _json_context(payload),
            BuyingSignalResult,
        )
        output = result.model_dump(mode="json")
        eligible_signals = []
        for signal in output["signals"]:
            source = eligible_source_text.get(signal["source_url"])
            if source is None:
                continue
            if not _contains_quote(source, signal["supporting_evidence"]):
                raise LocalAIError("Ollama signal did not quote text from a stored source; no signal was saved")
            eligible_signals.append(signal)
        output["signals"] = eligible_signals
        if not eligible_signals:
            output["insufficient_evidence"] = True
        await self.store.save_signals(product_id, prospect_id, output["signals"])
        await self.store.save_artifact(product_id, prospect_id, "buying_signals", output,
                                       [s["source_url"] for s in output["signals"]])
        return output

    async def generate_problem(self, product_id: str, prospect_id: str) -> dict:
        company, product, prospect, sources = await self.prospect(product_id, prospect_id)
        artifacts = await self.store.artifacts(product_id, prospect_id)
        latest = {row["workflow"]: row["content"] for row in reversed(artifacts)}
        source_list = [{"url": row["url"], "text": row["extracted_text"][:12000]} for row in sources]
        allowed_evidence = sorted(
            {f"prospect:{key}" for key, value in prospect.items() if value}
            | {row["url"] for row in sources}
        )
        result = await self.ai.generate_json(
            "problem_statement",
            "Write a prospect-specific, explicitly tentative problem hypothesis. Explain evidence and why the issue "
            "could matter, relate the selected product, and list assumptions still unverified. The evidence array must "
            "contain only exact strings from the allowed_evidence_references list. Use [] when no supplied item "
            "supports the hypothesis. Never invent or paraphrase an evidence reference, and never state an assumption "
            "as fact.\n\n" +
            _json_context({"seller": company, "selected_product": product, "prospect": prospect,
                           "cached_sources": source_list,
                           "product_specific_icp": product.get("icp"),
                           "product_specific_buying_signals": latest.get("buying_signals", {}),
                           "allowed_evidence_references": allowed_evidence}),
            ProblemStatement,
        )
        output = result.model_dump()
        if any(ref not in allowed_evidence for ref in output["evidence"]):
            raise LocalAIError("Problem statement cited evidence outside this prospect's stored research")
        await self.store.save_artifact(product_id, prospect_id, "problem_statement", output, output["evidence"])
        return output

    async def score(self, product_id: str, prospect_id: str) -> dict:
        company, product, prospect, sources = await self.prospect(product_id, prospect_id)
        icp = product.get("icp") or {}
        signals = await self.store.signals(product_id, prospect_id)
        source_text = " ".join(row["extracted_text"] for row in sources)
        body = " ".join([prospect.get("company_description", ""), source_text])
        industry_candidates = icp.get("target_industries", [])
        if industry_candidates and prospect.get("industry"):
            industry = _matching(prospect["industry"], industry_candidates)
        else:
            industry = 50

        size_text = str(icp.get("company_size", "")).lower()
        employee_count = prospect.get("employee_count")
        size_fit = 50
        if employee_count is not None and size_text:
            numbers = [int(n) for n in re.findall(r"\d+", size_text.replace(",", ""))]
            if len(numbers) >= 2:
                size_fit = 100 if numbers[0] <= employee_count <= numbers[1] else 20
            elif len(numbers) == 1:
                size_fit = 100 if employee_count <= numbers[0] else 25

        signal = round(100 * sum(float(row["confidence"]) for row in signals) / len(signals)) if signals else 0
        pain = _matching(body, product.get("customer_pain_points", []))
        alignment = _matching(body, [product.get("value_proposition", ""), *product.get("benefits", [])])
        completeness_fields = ("website", "industry", "location", "company_description", "employee_count",
                              "contact_name", "job_title", "business_email")
        completeness = round(100 * sum(bool(prospect.get(key)) for key in completeness_fields) /
                             len(completeness_fields))
        factors = {"industry_fit": industry, "company_size_fit": size_fit,
                   "buying_signals": signal, "pain_point_fit": pain,
                   "product_alignment": alignment, "data_completeness": completeness}
        weights = product.get("scoring_weights") or {}
        total_weight = sum(float(weights.get(k, 0)) for k in factors)
        if total_weight <= 0:
            raise WorkflowInputError("This product has no active scoring weights")
        score = round(sum(factors[k] * float(weights.get(k, 0)) for k in factors) / total_weight)
        level = "high" if score >= 85 else "qualified" if score >= 70 else "review" if score >= 45 else "low"
        missing = [key for key in completeness_fields if not prospect.get(key)]
        evidence = [f"Industry: {prospect.get('industry') or 'missing'}",
                    f"Company size: {employee_count if employee_count is not None else 'missing'}",
                    f"Product-specific verified buying signals: {len(signals)}",
                    f"Stored research sources: {len(sources)}"]
        result = {"score": score, "qualification_level": level, "factors": factors,
                  "weights": weights, "weighted_breakdown": {k: round(v * weights.get(k, 0), 2)
                                                                for k, v in factors.items()},
                  "evidence": evidence, "missing_information": missing,
                  "recommended_next_action": "Research missing company/contact fields" if missing else
                  "Review evidence and request a discovery conversation" if score >= 70 else
                  "Gather stronger product-fit evidence before prioritizing"}
        await self.store.save_artifact(product_id, prospect_id, "score", result, evidence)
        return result

    async def generate_email(self, product_id: str, prospect_id: str, style: str) -> dict:
        company, product, prospect, sources = await self.prospect(product_id, prospect_id)
        artifacts = await self.store.artifacts(product_id, prospect_id)
        latest = {row["workflow"]: row["content"] for row in reversed(artifacts)}
        if not latest.get("problem_statement"):
            raise WorkflowInputError("Generate the problem statement first so the email has grounded context")
        source_urls = {row["url"] for row in sources}
        payload = {"seller_company": company, "selected_product": product, "prospect": prospect,
                   "cached_sources": [{"url": row["url"], "text": row["extracted_text"][:10000]} for row in sources],
                   "product_specific_icp": product.get("icp"),
                   "buying_signals": latest.get("buying_signals", {}),
                   "problem_statement": latest["problem_statement"], "style": style}
        result = await self.ai.generate_json(
            "email_generation",
            "Draft one short personalized initial sales email in the requested style. Use only facts present in this "
            "context. Do not invent personal details, numbers, customers, outcomes, or claims. Mention uncertainties "
            "in assumptions rather than presenting them as facts. `evidence_used` must use only supplied source URLs "
            "or exact prospect fields. Include a low-pressure call to action.\n\n" + _json_context(payload), GeneratedEmail,
        )
        output = result.model_dump()
        allowed_refs = source_urls | {f"prospect:{key}" for key, value in prospect.items() if value}
        invalid = [ref for ref in output["evidence_used"] if ref not in allowed_refs]
        if invalid:
            raise LocalAIError("Generated email cited evidence outside this prospect's product context")
        await self.store.save_artifact(product_id, prospect_id, "email", output, output["evidence_used"])
        return output

    async def classify_reply(self, product_id: str, reply: str, sample: bool,
                             prospect_id: str | None = None) -> dict:
        company, product = await self.product(product_id)
        if prospect_id:
            prospect = await self.store.get_prospect(prospect_id)
            if not prospect or prospect["company_id"] != company["id"]:
                raise WorkflowInputError("Prospect does not belong to this product context")
        result = await self.ai.generate_json(
            "reply_classification",
            "Classify the supplied reply into the required category, state the sender's likely intent, and suggest a "
            "safe next action and concise response. `supporting_text` must be an exact quote from the reply. If the "
            "meaning is unclear use unknown. Respect unsubscribe requests. This may be a demonstration sample; it is "
            "not an actual customer interaction unless the caller says so.\n\n" +
            _json_context({"reply": reply, "product": product, "is_demo_sample": sample}), ReplyClassification,
        )
        output = result.model_dump(mode="json")
        if not _contains_quote(reply, output["supporting_text"]):
            raise LocalAIError("Reply classifier returned supporting text not found in the supplied reply")
        conversation = await self.store.save_conversation(product_id, prospect_id, reply, output, sample)
        await self.store.save_artifact(product_id, prospect_id, "reply_classification", output)
        return {**output, "conversation_id": conversation["id"], "sample": sample}


def _contains_quote(text: str, quote: str) -> bool:
    normalize = lambda value: " ".join((value or "").lower().split())
    return bool(normalize(quote)) and normalize(quote) in normalize(text)


class ResearchFinding(StrictModel):
    finding: str
    source_url: str
    evidence_excerpt: str
    evidence_type: str = Field(pattern="^(verified|extracted|inferred)$")
    confidence: float = Field(ge=0, le=1)


class ResearchSummary(StrictModel):
    overview: str
    findings: list[ResearchFinding]
    hypotheses: list[str]
    insufficient_evidence: bool

