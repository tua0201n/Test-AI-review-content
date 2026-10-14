"""Generic URL -> discovery -> adaptive workflow plan -> replay verification."""
from datetime import datetime, timezone
from pathlib import Path
import json
from .settings import RUNS
from .discovery import discover
from .demo_planner import plan_demo, validate_demo


async def prepare_demo(url, planner, max_pages=6, max_probes=12, folder=None):
    folder = Path(folder) if folder else RUNS / datetime.now(timezone.utc).strftime("prepare-demo-%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    manifest = {"input_url":url,"model":planner.model,"status":"discovering","ready_for_recording":False}
    def save():
        (folder/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    save()
    try:
        report = await discover(url,folder/"discovery",max_pages,max_probes,planner)
        manifest["discovery"] = "discovery/discovery.json"
        manifest["resolved_url"] = report.resolved_url
        if report.analysis_status != "complete" or report.status != "complete":
            manifest["status"] = "incomplete_discovery"
            save()
            return folder,manifest
        manifest["status"] = "planning"
        save()
        plan = await plan_demo(folder/"discovery/discovery.json",folder/"plan",planner)
        manifest.update(plan="plan/demo-plan.json",scope=plan.scope,product_type=plan.product_type)
        if not plan.flows:
            manifest["status"] = "insufficient_evidence"
            save()
            return folder,manifest
        manifest["status"] = "validating"
        save()
        validation = await validate_demo(folder/"plan/demo-plan.json",folder/"validation")
        manifest.update(validation="validation/validation.json",status="ready" if validation.status=="passed" else "needs_research",
                        ready_for_recording=validation.status=="passed")
        save()
        return folder,manifest
    except Exception as exc:
        # Save the failure type; CLI handles redaction of any provider error message.
        manifest.update(status="failed",error_type=type(exc).__name__)
        save()
        raise
