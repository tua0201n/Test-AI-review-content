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
    interaction_hint: Literal["", "tab", "filter", "disclosure", "media"] = ""


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
    resolved_url: str = ""
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


class DemoChoice(BaseModel):
    probe_id: str
    title: str
    purpose: str
    category: Literal["product_functionality", "ui_preference", "navigation"]


class DemoSelection(BaseModel):
    product_name: str
    audience: str
    choices: list[DemoChoice] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)


class WorkflowChoice(BaseModel):
    probe_ids: list[str] = Field(min_length=1, max_length=4)
    title: str
    purpose: str
    category: Literal["product_functionality", "ui_preference", "navigation"]


class WorkflowSelection(BaseModel):
    product_name: str
    product_type: str
    audience: str
    choices: list[WorkflowChoice] = Field(default_factory=list, max_length=3)
    limitations: list[str] = Field(default_factory=list)


class TargetFingerprint(BaseModel):
    tag: str
    label: str
    href: str = ""
    type: str = ""


class Checkpoint(BaseModel):
    kind: Literal["url_equals", "text_contains", "text_absent", "expanded_equals", "selected_equals"]
    expected: str


class DemoStep(BaseModel):
    operation: Literal["navigate", "click", "type", "select"]
    url: str = ""
    target: TargetFingerprint | None = None
    value: str = ""
    source_probe_id: str = ""
    checkpoints: list[Checkpoint] = Field(default_factory=list)


class DemoFlow(BaseModel):
    id: str
    source_probe_id: str
    source_probe_ids: list[str] = Field(default_factory=list)
    title: str
    purpose: str
    category: Literal["product_functionality", "ui_preference", "navigation"]
    initial_url: str
    steps: list[DemoStep]
    checkpoints: list[Checkpoint]


class DemoPlan(BaseModel):
    schema_version: str = "2.0"
    site_url: str = ""
    input_url: str
    source_report: str
    model: str
    product_name: str
    audience: str
    product_type: str = "unknown"
    scope: Literal["functional_demo", "limited_demo", "public_preview", "insufficient_evidence"]
    flows: list[DemoFlow] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CheckpointResult(BaseModel):
    step_index: int = 0
    checkpoint: Checkpoint
    actual: str
    passed: bool


class FlowValidation(BaseModel):
    flow_id: str
    status: Literal["passed", "failed", "blocked"]
    checkpoints: list[CheckpointResult] = Field(default_factory=list)
    before_screenshot: str = ""
    after_screenshot: str = ""
    step_screenshots: list[str] = Field(default_factory=list)
    reason: str = ""


class DemoValidation(BaseModel):
    source_plan: str
    status: Literal["passed", "partial", "failed", "blocked"]
    flows: list[FlowValidation] = Field(default_factory=list)


class StoryboardScene(BaseModel):
    id: str
    scene_type: Literal["hook", "demo", "benefit", "cta"]
    duration_seconds: int = Field(ge=2, le=15)
    headline: str = Field(max_length=100)
    voiceover: str = Field(max_length=420)
    caption: str = Field(max_length=140)
    visual_direction: str = Field(max_length=300)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    flow_id: str = ""
    step_index: int = -1


class StoryboardDraft(BaseModel):
    language: str
    tone: str
    scenes: list[StoryboardScene] = Field(min_length=3, max_length=12)
    limitations: list[str] = Field(default_factory=list)


class StoryboardReview(BaseModel):
    approved: bool
    unsupported_scene_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class Storyboard(BaseModel):
    schema_version: str = "1.0"
    status: Literal["ready", "needs_revision"]
    source_manifest: str
    source_plan: str
    source_validation: str
    source_discovery: str
    model: str
    product_name: str
    product_type: str
    audience: str
    language: str
    tone: str
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    total_duration_seconds: int
    scenes: list[StoryboardScene]
    review: StoryboardReview
    limitations: list[str] = Field(default_factory=list)


class ActionTrace(BaseModel):
    scene_id: str
    flow_id: str
    step_index: int
    operation: Literal["click", "type", "select"]
    target_label: str
    value: str = ""
    started_seconds: float
    ended_seconds: float
    cursor_from: list[float] = Field(min_length=2, max_length=2)
    cursor_to: list[float] = Field(min_length=2, max_length=2)
    checkpoints: list[CheckpointResult] = Field(default_factory=list)


class RecordedClip(BaseModel):
    scene_id: str
    flow_id: str
    step_index: int
    status: Literal["recorded", "failed"]
    duration_seconds: float
    raw_video: str = ""
    clip_video: str = ""
    poster: str = ""
    trace: ActionTrace | None = None
    reason: str = ""


class RecordingManifest(BaseModel):
    schema_version: str = "1.0"
    status: Literal["ready", "failed"]
    source_storyboard: str
    source_plan: str
    source_validation: str
    site_url: str
    viewport: dict[str, int]
    clips: list[RecordedClip] = Field(default_factory=list)
    narrative_scene_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class RenderedScene(BaseModel):
    scene_id: str
    scene_type: Literal["hook", "demo", "benefit", "cta"]
    duration_seconds: float
    video: str
    narration: str
    source_clip: str = ""
    source_poster: str = ""


class VideoManifest(BaseModel):
    schema_version: str = "1.0"
    status: Literal["ready", "failed"]
    source_storyboard: str
    source_recording: str
    resolution: str = "1280x720"
    fps: int = 30
    voice: str
    language: str
    total_duration_seconds: float
    scenes: list[RenderedScene] = Field(default_factory=list)
    output_video: str = ""
    subtitles: str = ""
    narration_mix: str = ""
    music: str = ""
    errors: list[str] = Field(default_factory=list)


class QualityCheck(BaseModel):
    name: str
    status: Literal["passed", "failed"]
    details: str


class DeliveryFile(BaseModel):
    path: str
    bytes: int
    sha256: str


class DeliveryManifest(BaseModel):
    schema_version: str = "1.0"
    status: Literal["ready", "failed"]
    product_name: str
    website: str
    duration_seconds: float
    resolution: str
    checks: list[QualityCheck] = Field(default_factory=list)
    files: list[DeliveryFile] = Field(default_factory=list)
    archive: str = ""
    errors: list[str] = Field(default_factory=list)
