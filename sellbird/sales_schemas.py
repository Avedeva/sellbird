"""Validated API and structured local-model payloads for the sales agent."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CompanyInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    industry: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=1000)
    company_size: str = Field(default="", max_length=100)
    target_geography: str = Field(default="", max_length=500)
    business_model: str = Field(default="", max_length=500)
    existing_sales_information: str = Field(default="", max_length=8000)


class ProductInput(StrictModel):
    company_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=8000)
    features: list[str] = Field(default_factory=list, max_length=30)
    benefits: list[str] = Field(default_factory=list, max_length=30)
    target_market: str = Field(default="", max_length=2000)
    pricing: str = Field(default="", max_length=1000)
    value_proposition: str = Field(default="", max_length=2000)
    competitive_differentiation: str = Field(default="", max_length=2000)
    customer_pain_points: list[str] = Field(default_factory=list, max_length=30)
    sales_positioning: str = Field(default="", max_length=2000)
    icp_criteria: dict[str, Any] = Field(default_factory=dict)
    scoring_weights: dict[str, float] = Field(default_factory=lambda: {
        "industry_fit": 0.20,
        "company_size_fit": 0.15,
        "buying_signals": 0.20,
        "pain_point_fit": 0.20,
        "product_alignment": 0.15,
        "data_completeness": 0.10,
    })

    @field_validator("scoring_weights")
    @classmethod
    def validate_scoring_weights(cls, value: dict[str, float]) -> dict[str, float]:
        allowed = {"industry_fit", "company_size_fit", "buying_signals",
                   "pain_point_fit", "product_alignment", "data_completeness"}
        if set(value) - allowed or not value or any(v < 0 for v in value.values()):
            raise ValueError("Scoring weights must use known factors and nonnegative values")
        if sum(value.values()) <= 0:
            raise ValueError("At least one scoring weight must be positive")
        total = sum(value.values())
        return {k: v / total for k, v in value.items()}


class ProspectInput(StrictModel):
    company_id: str = Field(min_length=1, max_length=40)
    company_name: str = Field(min_length=1, max_length=200)
    website: str = Field(default="", max_length=1000)
    industry: str = Field(default="", max_length=200)
    location: str = Field(default="", max_length=300)
    company_description: str = Field(default="", max_length=5000)
    employee_count: int | None = Field(default=None, ge=0, le=100_000_000)
    revenue_range: str = Field(default="", max_length=100)
    contact_name: str = Field(default="", max_length=200)
    job_title: str = Field(default="", max_length=200)
    business_email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=100)
    source_url: str = Field(default="", max_length=2000)
    field_provenance: dict[str, str] = Field(default_factory=dict)

    @field_validator("business_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.lower().strip()
        if value and not re.fullmatch(r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", value):
            raise ValueError("Business email must be a syntactically valid address")
        return value


class CSVImportInput(StrictModel):
    company_id: str = Field(min_length=1, max_length=40)
    csv_text: str = Field(min_length=1, max_length=5_000_000)


class ProspectDiscoveryInput(StrictModel):
    company_id: str = Field(min_length=1, max_length=40)
    product_id: str = Field(min_length=1, max_length=40)
    term: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=200)
    radius_km: int = Field(default=25, ge=1, le=80)
    limit: int = Field(default=25, ge=1, le=100)


class ResearchInput(StrictModel):
    max_pages: int = Field(default=4, ge=1, le=12)
    use_playwright: bool = False


class WorkflowInput(StrictModel):
    product_id: str = Field(min_length=1, max_length=40)


class EmailInput(WorkflowInput):
    style: str = Field(default="professional", pattern="^(professional|conversational|concise|consultative)$")


class ReplyInput(WorkflowInput):
    reply_text: str = Field(min_length=1, max_length=12000)
    sample: bool = False
    prospect_id: str | None = Field(default=None, max_length=40)


class BusinessProfile(StrictModel):
    positioning: str
    target_customers: list[str]
    customer_problems: list[str]
    value_proposition: str
    competitive_advantages: list[str]
    missing_information: list[str]


class ICPProfile(StrictModel):
    target_industries: list[str]
    company_size: str
    revenue_range: str
    geographic_markets: list[str]
    buyer_personas: list[str]
    decision_maker_roles: list[str]
    technology_stack: list[str]
    business_challenges: list[str]
    purchase_motivations: list[str]
    exclusion_criteria: list[str]
    qualification_criteria: list[str]


class SignalCategory(StrEnum):
    hiring = "hiring"
    expansion = "expansion"
    funding = "funding"
    product_launch = "product_launch"
    technology_adoption = "technology_adoption"
    leadership_change = "leadership_change"
    digital_transformation = "digital_transformation"
    operational_challenge = "operational_challenge"
    strategic_initiative = "strategic_initiative"
    other = "other"


class BuyingSignal(StrictModel):
    category: SignalCategory
    supporting_evidence: str
    source_url: str
    confidence: float = Field(ge=0, le=1)
    product_relevance: str
    business_implication: str
    potential_opportunity: str


class BuyingSignalResult(StrictModel):
    insufficient_evidence: bool
    signals: list[BuyingSignal]

    @model_validator(mode="after")
    def evidence_required(self):
        if self.insufficient_evidence and self.signals:
            raise ValueError("Insufficient-evidence results cannot contain signals")
        return self


class ProblemStatement(StrictModel):
    problem_hypothesis: str
    evidence: list[str]
    why_it_matters: str
    product_fit: str
    assumptions_to_verify: list[str]


class GeneratedEmail(StrictModel):
    subject: str
    body: str
    evidence_used: list[str]
    assumptions: list[str]


class ReplyCategory(StrEnum):
    interested = "interested"
    positive = "positive"
    meeting_requested = "meeting_requested"
    needs_more_information = "needs_more_information"
    objection = "objection"
    not_interested = "not_interested"
    not_now = "not_now"
    referral = "referral"
    out_of_office = "out_of_office"
    unsubscribe = "unsubscribe"
    unknown = "unknown"


class ReplyClassification(StrictModel):
    classification: ReplyCategory
    confidence: float = Field(ge=0, le=1)
    supporting_text: str
    intent: str
    recommended_next_action: str
    suggested_response: str


class HealthResponse(StrictModel):
    status: str
    ollama_reachable: bool
    configured_model: str
    model_available: bool
    offline_mode: bool
    error: str = ""

