"""Versioned data contracts for website discovery and its evidence."""
from typing import Literal
from pydantic import BaseModel, Field


class Control(BaseModel):
    id: str
    tag: str
    label: str
    type: str = ""
    href: str = ""
    role: str = ""
    form_submit: bool = False
    options: list[str] = Field(default_factory=list)
    expanded: str | None = None
    selected: str | None = None


class PageEvidence(BaseModel):
    id: str
    url: str
    title: str
    text: str
    screenshot: str
    controls: list[Control]
    requires_auth: bool = False


class ProbeRequest(BaseModel):
    control_id: str
    operation: Literal["click", "type", "select"]
    value: str = ""
    feature: str
    expected_observation: str


class ExplorationPlan(BaseModel):
    product_name: str = ""
    page_purpose: str
    probes: list[ProbeRequest] = Field(default_factory=list, max_length=3)
    priority_urls: list[str] = Field(default_factory=list, max_length=8)


class ProbeEvidence(BaseModel):
    id: str
    page_id: str
    request: ProbeRequest
    status: Literal["demonstrated", "no_observable_result", "blocked_auth", "blocked_action", "failed"]
    before: PageEvidence
    after: PageEvidence | None = None
    observed_changes: list[str] = Field(default_factory=list)
    reason: str
    target_fingerprint: str = ""


class ProductClaim(BaseModel):
    description: str
    source_page_ids: list[str]


class ProductBrief(BaseModel):
    product_name: str
    positioning: str
    audience_hypotheses: list[str] = Field(default_factory=list)
    advertised_features: list[ProductClaim] = Field(default_factory=list)
    recommended_demo_probe_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class DiscoveryReport(BaseModel):
    schema_version: str = "1.0"
    input_url: str
    started_at: str
    status: Literal["complete", "partial", "failed"] = "complete"
    mode: Literal["llm", "offline"]
    model: str | None = None
    analysis_status: Literal["pending", "complete", "unavailable", "not_requested"] = "not_requested"
    pages: list[PageEvidence] = Field(default_factory=list)
    probes: list[ProbeEvidence] = Field(default_factory=list)
    brief: ProductBrief | None = None
    errors: list[str] = Field(default_factory=list)
