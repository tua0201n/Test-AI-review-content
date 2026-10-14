"""Generate an evidence-grounded marketing storyboard from a verified Task 2 run."""
import json
from importlib.resources import files
from pathlib import Path
from .models import (DemoPlan, DemoValidation, DiscoveryReport, StoryboardDraft,
                     StoryboardReview, Storyboard)

STORYBOARD_SYSTEM = files("marketing_video").joinpath("prompts/storyboard.txt").read_text(encoding="utf-8")


def _inside(root, value, label):
    root = root.resolve()
    path = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    if not path.is_relative_to(root):
        raise ValueError(label + " must stay inside the Task 2 run folder")
    if not path.is_file():
        raise ValueError(label + " does not exist: " + str(path))
    return path


def load_sources(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "ready" or manifest.get("ready_for_recording") is not True:
        raise ValueError("Task 2 manifest is not ready_for_recording")
    root = manifest_path.parent
    plan_path = _inside(root, manifest.get("plan", ""), "plan")
    validation_path = _inside(root, manifest.get("validation", ""), "validation")
    discovery_path = _inside(root, manifest.get("discovery", ""), "discovery")
    plan = DemoPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    validation = DemoValidation.model_validate_json(validation_path.read_text(encoding="utf-8"))
    discovery = DiscoveryReport.model_validate_json(discovery_path.read_text(encoding="utf-8"))
    if validation.status != "passed":
        raise ValueError("Task 2 validation is not passed")
    if Path(validation.source_plan).resolve() != plan_path:
        raise ValueError("Validation does not belong to the manifest plan")
    return manifest_path, plan_path, validation_path, discovery_path, plan, validation, discovery


def evidence_bundle(plan, validation, discovery):
    passed = {x.flow_id:x for x in validation.flows if x.status == "passed"}
    probes = {p.id:p for p in discovery.probes}
    catalog = {
        "product": {"kind":"product_identity", "product_name":plan.product_name,
                    "product_type":plan.product_type, "audience":plan.audience}
    }
    flows = []
    for flow in plan.flows:
        result = passed.get(flow.id)
        if not result:
            continue
        catalog["flow:"+flow.id] = {"kind":"passed_flow", "title":flow.title,
            "purpose":flow.purpose, "category":flow.category}
        item = {"id":flow.id, "title":flow.title, "purpose":flow.purpose, "steps":[]}
        passed_steps = {c.step_index for c in result.checkpoints if c.passed}
        for index,step in enumerate(flow.steps):
            if step.operation == "navigate":
                continue
            if index not in passed_steps:
                raise ValueError(f"Passed flow {flow.id} has no passed checkpoint for step {index}")
            probe = probes.get(step.source_probe_id)
            evidence_id = f"step:{flow.id}:{index}"
            entry = {"kind":"demonstrated_step", "flow_id":flow.id, "step_index":index,
                "operation":step.operation, "target":step.target.label if step.target else "",
                "value":step.value, "checkpoints":[c.model_dump() for c in step.checkpoints],
                "observed_result":probe.reason if probe else "Verified by Task 2 replay"}
            catalog[evidence_id] = entry
            item["steps"].append({"evidence_id":evidence_id, **entry})
        flows.append(item)
    if not flows:
        raise ValueError("No passed workflow is available for a storyboard")
    if discovery.brief:
        for index,claim in enumerate(discovery.brief.advertised_features):
            catalog[f"claim:{index}"] = {"kind":"advertised_claim", "description":claim.description,
                "source_page_ids":claim.source_page_ids}
    limitations = list(dict.fromkeys(plan.limitations + (discovery.brief.limitations if discovery.brief else [])))
    for index,text in enumerate(limitations):
        catalog[f"limitation:{index}"] = {"kind":"limitation", "description":text}
    return {"product":{"name":plan.product_name,"type":plan.product_type,"audience":plan.audience},
            "flows":flows,"evidence_catalog":catalog,"limitations":limitations}


def validate_draft(draft, plan, validation, evidence, target_duration):
    scenes = draft.scenes
    if len({s.id for s in scenes}) != len(scenes):
        raise ValueError("Scene IDs must be unique")
    if scenes[0].scene_type != "hook" or scenes[-1].scene_type != "cta":
        raise ValueError("Storyboard must start with hook and end with CTA")
    if sum(s.scene_type=="hook" for s in scenes) != 1 or sum(s.scene_type=="cta" for s in scenes) != 1:
        raise ValueError("Storyboard needs exactly one hook and one CTA")
    total = sum(s.duration_seconds for s in scenes)
    if total < max(20,target_duration-5) or total > min(90,target_duration+5):
        raise ValueError(f"Storyboard duration {total}s is outside the allowed target range")
    allowed = set(evidence["evidence_catalog"])
    claim_ids = {key for key,value in evidence["evidence_catalog"].items()
                 if value.get("kind") == "advertised_claim"}
    passed = {x.flow_id for x in validation.flows if x.status=="passed"}
    flows = {x.id:x for x in plan.flows if x.id in passed}
    used = {}
    for scene in scenes:
        if scene.scene_type != "cta" and not scene.evidence_ids:
            raise ValueError("Every non-CTA scene needs evidence IDs: " + scene.id)
        unknown = set(scene.evidence_ids)-allowed
        if unknown:
            raise ValueError("Unknown evidence IDs in "+scene.id+": "+", ".join(sorted(unknown)))
        if scene.scene_type == "demo":
            if scene.flow_id not in flows or scene.step_index < 1:
                raise ValueError("Demo scene references an unverified flow or step: "+scene.id)
            key = f"step:{scene.flow_id}:{scene.step_index}"
            if key not in scene.evidence_ids:
                raise ValueError("Demo scene must cite its exact step evidence: "+scene.id)
            flow = flows[scene.flow_id]
            if scene.step_index >= len(flow.steps) or flow.steps[scene.step_index].operation=="navigate":
                raise ValueError("Demo step is outside the workflow: "+scene.id)
            used.setdefault(scene.flow_id,[]).append(scene.step_index)
        elif scene.scene_type == "benefit":
            if not set(scene.evidence_ids) & claim_ids:
                raise ValueError("Benefit scene must cite an advertised claim: "+scene.id)
            if scene.flow_id or scene.step_index != -1:
                raise ValueError("Only demo scenes may bind to a workflow step: "+scene.id)
        elif scene.flow_id or scene.step_index != -1:
            raise ValueError("Only demo scenes may bind to a workflow step: "+scene.id)
    if not used:
        raise ValueError("Storyboard must contain at least one demonstrated workflow")
    if claim_ids and not any(scene.scene_type == "benefit" for scene in scenes):
        raise ValueError("Storyboard must include a benefit scene when advertised claims are available")
    for flow_id,indexes in used.items():
        expected = [i for i,s in enumerate(flows[flow_id].steps) if s.operation!="navigate"]
        if indexes != expected:
            raise ValueError(f"Storyboard must cover passed flow {flow_id} once and in order: expected {expected}")
    return total


def markdown(storyboard):
    lines = ["# Marketing storyboard","",storyboard.product_name,
             f"Status: {storyboard.status} | Duration: {storyboard.total_duration_seconds}s | Ratio: {storyboard.aspect_ratio}",
             f"Audience: {storyboard.audience}",""]
    cursor = 0
    for scene in storyboard.scenes:
        end = cursor + scene.duration_seconds
        lines += [f"## {scene.id} · {cursor:02d}–{end:02d}s · {scene.scene_type}","",
                  "**Headline:** "+scene.headline,"","**Voiceover:** "+scene.voiceover,"",
                  "**Caption:** "+scene.caption,"","**Visual:** "+scene.visual_direction,"",
                  "Evidence: "+(", ".join(scene.evidence_ids) or "CTA only"),""]
        cursor = end
    lines += ["## Editorial review","", "Approved: "+str(storyboard.review.approved)]
    lines += ["- "+x for x in storyboard.review.notes]
    if storyboard.limitations:
        lines += ["","## Limitations",""]+["- "+x for x in storyboard.limitations]
    return "\n".join(lines)+"\n"


async def create_storyboard(manifest_path, folder, planner, language="vi", target_duration=40, aspect_ratio="16:9"):
    (manifest_path, plan_path, validation_path, discovery_path,
     plan, validation, discovery) = load_sources(manifest_path)
    evidence = evidence_bundle(plan,validation,discovery)
    request = {**evidence,"language":language,"target_duration_seconds":target_duration,
               "aspect_ratio":aspect_ratio,"requirements":{
                   "first_scene":"hook","last_scene":"cta",
                   "demo_coverage":"Choose at least one passed flow and include every action step exactly once in order",
                   "evidence":"Every non-CTA scene cites only evidence_catalog IDs",
                   "duration_range":[max(20,target_duration-5),min(90,target_duration+5)],
                   "benefit":"When advertised claims exist, include a benefit scene citing at least one claim ID"}}
    instruction = ("Create a concise product marketing storyboard. A demo scene maps to exactly one action step. "
        "Use flow_id and step_index only on demo scenes; use empty flow_id and -1 elsewhere. "
        "The CTA may have no evidence IDs and should invite the viewer to learn more or try the product without promising results. "
        "Do not expose internal evidence IDs in headline, voiceover or caption.")
    draft = None
    review = StoryboardReview(approved=False,notes=["Not reviewed"])
    compiler_feedback = ""
    for attempt in range(2):
        payload = dict(request)
        if compiler_feedback:
            payload["revision_feedback"] = compiler_feedback
        draft = await planner.invoke(instruction,payload,StoryboardDraft,system_prompt=STORYBOARD_SYSTEM)
        try:
            total = validate_draft(draft,plan,validation,evidence,target_duration)
        except ValueError as exc:
            if attempt:
                raise
            compiler_feedback = str(exc)
            continue
        review_payload = {"storyboard":draft.model_dump(),"evidence_catalog":evidence["evidence_catalog"],
                          "limitations":evidence["limitations"]}
        review = await planner.invoke(
            "Audit every scene. Reject unsupported or exaggerated claims, claims that confuse advertised copy with demonstrated behavior, "
            "and descriptions of write actions that were not replayed. Treat product_identity strictly as identity, type and audience; "
            "it cannot support promises about speed, ease, effectiveness, improvement or outcomes. A benefit must stay within the exact "
            "meaning of its cited advertised_claim. unsupported_scene_ids must use existing scene IDs.",
            review_payload,StoryboardReview,system_prompt=STORYBOARD_SYSTEM)
        unknown = set(review.unsupported_scene_ids)-{s.id for s in draft.scenes}
        if unknown:
            review = review.model_copy(update={"approved":False,"notes":review.notes+["Reviewer returned unknown scene IDs"]})
        if review.approved and not review.unsupported_scene_ids:
            break
        if attempt == 0:
            compiler_feedback = "Editorial review rejected scenes: "+", ".join(review.unsupported_scene_ids)+". "+"; ".join(review.notes)
    status = "ready" if review.approved and not review.unsupported_scene_ids else "needs_revision"
    total = validate_draft(draft,plan,validation,evidence,target_duration)
    storyboard = Storyboard(status=status,source_manifest=str(manifest_path),source_plan=str(plan_path),
        source_validation=str(validation_path),source_discovery=str(discovery_path),model=planner.model,
        product_name=plan.product_name,product_type=plan.product_type,audience=plan.audience,
        language=draft.language,tone=draft.tone,aspect_ratio=aspect_ratio,total_duration_seconds=total,
        scenes=draft.scenes,review=review,limitations=list(dict.fromkeys(evidence["limitations"]+draft.limitations)))
    folder=Path(folder)
    folder.mkdir(parents=True)
    (folder/"evidence.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
    (folder/"storyboard-draft.json").write_text(draft.model_dump_json(indent=2),encoding="utf-8")
    (folder/"review.json").write_text(review.model_dump_json(indent=2),encoding="utf-8")
    (folder/"storyboard.json").write_text(storyboard.model_dump_json(indent=2),encoding="utf-8")
    (folder/"storyboard.md").write_text(markdown(storyboard),encoding="utf-8")
    return storyboard
