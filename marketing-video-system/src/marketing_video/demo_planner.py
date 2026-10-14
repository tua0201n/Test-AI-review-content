"""Select product-specific workflows from evidence and replay every step."""
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright
from .models import (DiscoveryReport, DemoSelection, WorkflowSelection, TargetFingerprint, DemoStep, DemoFlow, DemoPlan,
                     Checkpoint, CheckpointResult, FlowValidation, DemoValidation, ProbeRequest)
from .auth import session_for
from .discovery import same_site, permitted, settle, snapshot, target_state

UI_PREF = re.compile(r'language|ngôn ngữ|theme|dark mode|light mode', re.I)
LOADING = re.compile(r'(?im)^\s*(loading(?:\.\.\.|…)?|đang tải(?:\.\.\.|…)?)\s*$')


def find_control(page, target):
    matches = [c for c in page.controls if (c.tag,c.label,c.href,c.type) ==
               (target.tag,target.label,target.href,target.type)]
    return matches[0] if len(matches) == 1 else None


def checkpoints_for(probe, target):
    if not probe.after or LOADING.search(probe.after.text):
        return []
    points = []
    if probe.before.url != probe.after.url:
        points.append(Checkpoint(kind="url_equals", expected=probe.after.url))
    old, new = find_control(probe.before, target), find_control(probe.after, target)
    if old and new:
        if old.expanded != new.expanded and new.expanded is not None:
            points.append(Checkpoint(kind="expanded_equals", expected=new.expanded))
        if old.selected != new.selected and new.selected is not None:
            points.append(Checkpoint(kind="selected_equals", expected=new.selected))
    old_lines = {x.strip() for x in probe.before.text.splitlines()}
    new_lines = [x.strip() for x in probe.after.text.splitlines()]
    def stable(x):
        return len(x) >= 4 and not re.fullmatch(r'[\d\s.,%+$/-]+',x) and x != probe.request.value and not LOADING.search(x)
    added = [x for x in new_lines if x and x not in old_lines and stable(x)]
    if added:
        points.append(Checkpoint(kind="text_contains", expected=added[0][:180]))
    # Filtering can remove results without adding a new text line.
    if probe.request.operation in {"type","select"} and probe.before.url == probe.after.url:
        missing = [x.strip() for x in probe.before.text.splitlines() if x.strip() not in set(new_lines) and stable(x.strip())]
        if missing:
            points.append(Checkpoint(kind="text_absent",expected=missing[0][:180]))
            retained = [x for x in new_lines if stable(x) and x in old_lines]
            if retained:
                points.append(Checkpoint(kind="text_contains",expected=max(retained,key=len)[:180]))
    if points and not any(p.kind=="url_equals" for p in points):
        points.insert(0,Checkpoint(kind="url_equals",expected=probe.after.url))
    return points


EMPTY_RESULT = re.compile(r'(?i)\bno (?:\w+ ){0,5}(?:yet|found|available|matching)|nothing to|no (?:results|matches|items|learners|tasks|courses)|there (?:are|is) (?:currently )?no|không có|chưa có|danh sách trống')


def evidence_quality(probe):
    added = [x.strip() for x in probe.after.text.splitlines() if x.strip() and x.strip() not in set(probe.before.text.splitlines())]
    if any(EMPTY_RESULT.search(x) for x in added):
        return "empty_state"
    if not added and probe.before.url==probe.after.url:
        return "state_only"
    return "content_result"


def research_root(report):
    return report.resolved_url or (report.pages[0].url if report.pages else report.input_url)


def eligible_probes(report):
    output = []
    root = research_root(report)
    for p in report.probes:
        if p.status != "demonstrated" or not p.target_fingerprint or not p.after:
            continue
        if evidence_quality(p) == "empty_state":
            continue
        target = TargetFingerprint.model_validate_json(p.target_fingerprint)
        control = find_control(p.before,target)
        if not control or not same_site(p.before.url,root) or not same_site(p.after.url,root):
            continue
        if p.before.requires_auth or p.after.requires_auth or permitted(control,p.request,root):
            continue
        if checkpoints_for(p,target):
            output.append(p)
    return output


def can_follow(previous, following):
    return (previous.after.url == following.before.url and
            find_control(previous.after,TargetFingerprint.model_validate_json(following.target_fingerprint)) is not None)


def compile_plan(selection, report, source):
    proven = {p.id:p for p in eligible_probes(report)}
    flows, seen = [], set()
    limitations = list(selection.limitations)
    for choice in selection.choices:
        ids = list(choice.probe_ids) if hasattr(choice,"probe_ids") else [choice.probe_id]
        if len(ids) != len(set(ids)):
            raise ValueError("A workflow repeats a probe")
        probes = []
        for pid in ids:
            if pid not in proven:
                raise ValueError("Selected probe has no demonstrated evidence or is not replayable: " + pid)
            probes.append(proven[pid])
        for previous,following in zip(probes,probes[1:]):
            if not can_follow(previous,following):
                raise ValueError("Evidence does not support a continuous workflow: " + previous.id + " -> " + following.id)
        identity = tuple((p.before.url,p.target_fingerprint,p.request.operation,p.request.value) for p in probes)
        if identity in seen:
            continue
        seen.add(identity)
        steps = [DemoStep(operation="navigate",url=probes[0].before.url)]
        for p in probes:
            target = TargetFingerprint.model_validate_json(p.target_fingerprint)
            steps.append(DemoStep(operation=p.request.operation,target=target,value=p.request.value,
                source_probe_id=p.id,checkpoints=checkpoints_for(p,target)))
        category = choice.category
        if all(UI_PREF.search(p.request.feature + " " + json.loads(p.target_fingerprint)["label"]) for p in probes):
            category = "ui_preference"
        # Links may open useful detail/results pages; do not force all links to navigation.
        flows.append(DemoFlow(id="demo-"+str(len(flows)+1).zfill(2),source_probe_id=ids[0],source_probe_ids=ids,
            title=choice.title,purpose=choice.purpose,category=category,initial_url=probes[0].before.url,
            steps=steps,checkpoints=steps[-1].checkpoints))
    scope = "insufficient_evidence" if not flows else "functional_demo" if any(f.category=="product_functionality" for f in flows) else "limited_demo"
    if scope == "limited_demo":
        limitations.append("Only navigation or UI preferences are supported by the selected evidence")
    if any(p.requires_auth for p in report.pages):
        limitations.append("Some researched pages are authentication-gated; no unproven authenticated behavior is included")
    return DemoPlan(input_url=report.input_url,site_url=research_root(report),source_report=str(source.resolve()),model=report.model or "unknown",
        product_name=selection.product_name,product_type=getattr(selection,"product_type","unknown"),
        audience=selection.audience,scope=scope,flows=flows,limitations=list(dict.fromkeys(limitations)))


def compact_evidence(p):
    old_lines = set(p.before.text.splitlines())
    new_lines = set(p.after.text.splitlines())
    return {"id":p.id,"feature":p.request.feature,"operation":p.request.operation,"value":p.request.value,
        "target":json.loads(p.target_fingerprint),"before_url":p.before.url,"after_url":p.after.url,
        "quality":evidence_quality(p),"observations":p.observed_changes,"added_text":list(sorted(new_lines-old_lines))[:16],
        "removed_text":list(sorted(old_lines-new_lines))[:16],"after_text":p.after.text[:1000]}


async def plan_demo(source, folder, planner):
    report = DiscoveryReport.model_validate_json(source.read_text(encoding="utf-8"))
    if report.analysis_status != "complete" or report.brief is None:
        raise ValueError("Complete an LLM-backed discovery with a product brief before planning a demo")
    eligible = eligible_probes(report)
    edges = [{"from":a.id,"to":b.id} for a in eligible for b in eligible if a.id!=b.id and can_follow(a,b)]
    brief_data = report.brief.model_dump()
    brief_data["recommended_demo_probe_ids"] = [x for x in brief_data["recommended_demo_probe_ids"] if x in {p.id for p in eligible}]
    data = {"input_url":report.input_url,"brief":brief_data,
        "eligible_probes":[compact_evidence(p) for p in eligible],"continuity_edges":edges}
    instruction = (
        "Infer this product's type and audience from evidence; no workflow or website is predetermined. "
        "Choose up to 3 distinct marketing demo workflows, fewer when only one strong task exists. Each choice contains an ordered probe_ids list of 1-4 existing IDs. "
        "For every consecutive pair use ONLY continuity_edges; do not combine unrelated screens or insert invented actions. "
        "Prefer one useful multi-step task (e.g. find an item then inspect it) over isolated clicks. "
        "Choose tasks appropriate to THIS product, not a fixed education/ecommerce template. "
        "Do not pad the video to three flows. Prefer content_result over state_only. Avoid empty-state tasks as primary demos, duplicate navigation, language menus, or claims of untested write actions. "
        "A link opening meaningful product details can be product_functionality. Opening a tab with an empty list does not prove completing a task. "
        "If evidence is insufficient return empty choices and explain missing evidence. Respond in Vietnamese."
    )
    selection = None
    for attempt in range(2):
        selection = await planner.invoke(instruction,data,WorkflowSelection)
        try:
            plan = compile_plan(selection,report,source)
            break
        except ValueError as exc:
            if attempt:
                raise
            data["compiler_feedback"] = str(exc)
    plan.model = planner.model
    folder.mkdir(parents=True)
    (folder/"selection.json").write_text(selection.model_dump_json(indent=2),encoding="utf-8")
    (folder/"demo-plan.json").write_text(plan.model_dump_json(indent=2),encoding="utf-8")
    lines = ["# Adaptive demo plan","",plan.product_name,"Product type: "+plan.product_type,
             "Scope: "+plan.scope,"","Audience: "+plan.audience,""]
    for f in plan.flows:
        lines += ["## "+f.id+": "+f.title,"",f.purpose,"Evidence: "+", ".join(f.source_probe_ids),"Start: "+f.initial_url]
        for i,step in enumerate(f.steps):
            lines += [f"- Step {i}: {step.operation} "+(step.target.label if step.target else step.url)]
            lines += ["  - "+c.kind+": "+c.expected for c in step.checkpoints]
    lines += ["","## Limitations",""]+["- "+x for x in plan.limitations]
    (folder/"demo-plan.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return plan


def check_point(point, after, state, step_index):
    if point.kind == "url_equals":
        actual,passed = after.url,after.url==point.expected
    elif point.kind in {"text_contains","text_absent"}:
        present = point.expected in after.text
        passed = present if point.kind=="text_contains" else not present
        actual = "[text present]" if present else "[text absent]"
    else:
        key = "expanded" if point.kind=="expanded_equals" else "selected"
        actual = str(state.get(key))
        passed = actual==point.expected
    return CheckpointResult(step_index=step_index,checkpoint=point,actual=actual,passed=passed)


async def validate_demo(plan_path, folder, visible=False):
    plan = DemoPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    root = plan.site_url or plan.input_url
    folder.mkdir(parents=True)
    (folder/"screenshots").mkdir()
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not visible)
        try:
            for flow in plan.flows:
                context = await browser.new_context(viewport={"width":1280,"height":720},accept_downloads=False,storage_state=session_for(root))
                page = await context.new_page()
                entry = FlowValidation(flow_id=flow.id,status="failed")
                try:
                    if not flow.checkpoints or not flow.steps or flow.steps[0].operation!="navigate":
                        raise ValueError("Flow needs an initial navigation and evidence checkpoints")
                    new_state = {}
                    after = None
                    for i,step in enumerate(flow.steps):
                        if step.operation=="navigate":
                            if i!=0 or not same_site(step.url,root):
                                raise ValueError("Only the initial same-site navigation is allowed")
                            await page.goto(step.url,wait_until="domcontentloaded",timeout=30000)
                            await settle(page)
                            if not same_site(page.url,root):
                                raise ValueError("Initial navigation redirected outside the product")
                            continue
                        if step.target is None:
                            raise ValueError("Missing target fingerprint")
                        initial = await snapshot(page,folder,f"{flow.id}-step-{i}-before")
                        if not entry.before_screenshot:
                            entry.before_screenshot = initial.screenshot
                        if initial.requires_auth:
                            entry.status="blocked"
                            raise ValueError("Requires an authorized product session")
                        control = find_control(initial,step.target)
                        if control is None:
                            raise ValueError("Evidence target is missing or ambiguous in the current workflow state")
                        req=ProbeRequest(control_id=control.id,operation=step.operation,value=step.value,
                            feature=flow.title,expected_observation="Per-step checkpoint verification")
                        reason=permitted(control,req,root)
                        if reason:
                            entry.status="blocked"
                            raise ValueError(reason)
                        target=page.locator('[data-mv-id="'+control.id+'"]')
                        if step.operation=="click":
                            await target.click(timeout=10000)
                        elif step.operation=="type":
                            await target.fill(step.value)
                        else:
                            await target.select_option(step.value)
                        await settle(page)
                        new_state=await target_state(target) if await target.count() and page.url==initial.url else {}
                        after=await snapshot(page,folder,f"{flow.id}-step-{i}-after")
                        entry.step_screenshots.append(after.screenshot)
                        entry.after_screenshot=after.screenshot
                        if not same_site(after.url,root) or after.requires_auth or LOADING.search(after.text):
                            raise ValueError("No usable same-site result was loaded")
                        if plan.schema_version=="2.0" and not step.checkpoints:
                            raise ValueError("Each action needs evidence checkpoints")
                        checks=[check_point(p,after,new_state,i) for p in step.checkpoints]
                        entry.checkpoints.extend(checks)
                        if any(not p.passed for p in checks):
                            raise ValueError(f"Checkpoint mismatch at step {i}; workflow stopped")
                    if after is None:
                        raise ValueError("Workflow performed no action")
                    # Schema 2 stores final checkpoints on the last action as well as
                    # the legacy flow field. They were already checked above.
                    if plan.schema_version != "2.0":
                        entry.checkpoints.extend(check_point(p,after,new_state,len(flow.steps)-1) for p in flow.checkpoints)
                    entry.status="passed" if all(c.passed for c in entry.checkpoints) else "failed"
                    entry.reason="All step and final checkpoints passed" if entry.status=="passed" else "Final checkpoint mismatch"
                except Exception as exc:
                    entry.reason=type(exc).__name__+": "+str(exc)[:600]
                finally:
                    results.append(entry)
                    print("Replay:",entry.flow_id,entry.status,entry.reason,flush=True)
                    await context.close()
        finally:
            await browser.close()
    status="blocked" if not results else "passed" if all(x.status=="passed" for x in results) else "partial" if any(x.status=="passed" for x in results) else "failed"
    report=DemoValidation(source_plan=str(plan_path.resolve()),status=status,flows=results)
    (folder/"validation.json").write_text(report.model_dump_json(indent=2),encoding="utf-8")
    lines=["# Demo replay validation","","Status: "+status,""]
    for f in results:
        lines += ["- "+f.flow_id+": "+f.status+" — "+f.reason]
    (folder/"validation.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return report
