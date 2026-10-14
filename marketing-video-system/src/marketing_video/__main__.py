"""Commands for configuration checks, Gemini smoke tests and website discovery."""
import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlparse
from pydantic import BaseModel
from .settings import Settings, ROOT, RUNS


class ConnectionResult(BaseModel):
    ok: bool
    message: str


async def check_environment(settings, test_browser=False):
    from playwright.async_api import async_playwright
    print("Project:", ROOT)
    print("Python:", sys.version.split()[0])
    for name in ["browser-use", "google-genai", "playwright"]:
        print(name + ":", version(name))
    print("Provider:", settings.provider)
    print("Model:", settings.model)
    key = settings.google_api_key if settings.provider in {"google", "gemini"} else settings.browser_use_api_key if settings.provider == "browser-use" else settings.openai_api_key
    print("API key:", "configured" if key.get_secret_value() else "missing - edit .env")
    async with async_playwright() as pw:
        exists = Path(pw.chromium.executable_path).exists()
        print("Chromium:", "OK" if exists else "missing - run setup.ps1")
        if test_browser and exists:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content("<title>Environment OK</title><button>Ready</button>")
                if await page.title() != "Environment OK":
                    raise RuntimeError("Browser environment test failed")
                print("Browser launch:", "OK")
            finally:
                await browser.close()
    return 0 if exists else 2


async def test_llm(settings):
    from .llm import Planner
    planner = Planner(settings)
    result = await planner.invoke("This is a connection test, not website discovery. Return ok=true and message='Gemini connection OK' if you can respond.", {}, ConnectionResult)
    if not result.ok:
        raise RuntimeError("Model did not confirm the connection test")
    target = RUNS / datetime.now(timezone.utc).strftime("llm-test-%Y%m%d-%H%M%S-%f")
    target.mkdir(parents=True)
    payload = {"provider": planner.provider, "model": planner.model, "result": result.model_dump()}
    (target / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("LLM connection: OK")
    print("Provider:", planner.provider)
    print("Model:", planner.model)
    print("Saved:", target / "result.json")
    return 0


def main():
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="URL → marketing-video system")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="Check packages, browser and key presence without calling an LLM")
    check.add_argument("--browser", action="store_true")
    sub.add_parser("test-llm", help="Make one structured LLM request using the configured provider")
    research = sub.add_parser("discover", help="Discover website functionality from a URL")
    research.add_argument("url")
    research.add_argument("--max-pages", type=int, default=settings.max_pages)
    research.add_argument("--max-probes", type=int, default=settings.max_probes)
    research.add_argument("--offline", action="store_true")
    research.add_argument("--visible", action="store_true")
    prepare = sub.add_parser("prepare-demo", help="Prepare and verify product-specific demo workflows from any URL")
    prepare.add_argument("url")
    prepare.add_argument("--max-pages",type=int,default=settings.max_pages)
    prepare.add_argument("--max-probes",type=int,default=12)
    recheck = sub.add_parser("recheck-discovery", help="Replay AI-selected discovery probes against fresh pages")
    recheck.add_argument("discovery",type=Path)
    recheck.add_argument("--offline",action="store_true")
    demo = sub.add_parser("plan-demo", help="Choose evidence-backed demo flows with Gemini")
    demo.add_argument("discovery", type=Path)
    replay = sub.add_parser("validate-demo", help="Replay planned flows and check real results")
    replay.add_argument("plan", type=Path)
    replay.add_argument("--visible", action="store_true")
    story = sub.add_parser("storyboard", help="Write and audit a marketing storyboard from a ready Task 2 manifest")
    story.add_argument("manifest", type=Path)
    story.add_argument("--language", default="vi")
    story.add_argument("--duration", type=int, default=40)
    story.add_argument("--aspect-ratio", choices=["16:9","9:16","1:1"], default="16:9")
    record = sub.add_parser("record-scenes", help="Record verified storyboard demo scenes with an animated cursor")
    record.add_argument("storyboard", type=Path)
    record.add_argument("--visible", action="store_true")
    compose = sub.add_parser("compose-video", help="Create TTS, captions, graphics and the final marketing MP4")
    compose.add_argument("storyboard", type=Path)
    compose.add_argument("recording", type=Path)
    compose.add_argument("--voice", default="")
    package = sub.add_parser("package-video", help="Run final QA and create a sanitized delivery ZIP")
    package.add_argument("video_manifest", type=Path)
    login_cmd = sub.add_parser("login", help="Capture an authorized demo session through manual browser login")
    login_cmd.add_argument("url")
    import_cmd = sub.add_parser("import-session", help="Import an existing Playwright session JSON")
    import_cmd.add_argument("url")
    import_cmd.add_argument("session", type=Path)
    args = parser.parse_args()
    if args.command == "check":
        return asyncio.run(check_environment(settings, args.browser))
    if args.command == "test-llm":
        return asyncio.run(test_llm(settings))
    if args.command == "import-session":
        from .auth import import_session_file
        parsed = urlparse(args.url)
        if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.username or parsed.password:
            parser.error("Provide a valid product URL without credentials")
        import_session_file(args.session,args.url)
        return 0
    if args.command == "login":
        from .auth import login
        parsed = urlparse(args.url)
        if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.username or parsed.password:
            parser.error("Provide a valid login URL without credentials")
        asyncio.run(login(args.url))
        return 0
    if args.command == "prepare-demo":
        parsed = urlparse(args.url)
        if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.username or parsed.password:
            parser.error("Provide a valid product URL without embedded credentials")
        if not 1<=args.max_pages<=20 or not 0<=args.max_probes<=20:
            parser.error("--max-pages must be 1-20; --max-probes must be 0-20")
        from .pipeline import prepare_demo
        from .llm import Planner
        folder,manifest = asyncio.run(prepare_demo(args.url,Planner(settings),args.max_pages,args.max_probes))
        print("Status:",manifest["status"])
        print("Ready for recording:",manifest["ready_for_recording"])
        print("Manifest:",folder / "manifest.json")
        return 0 if manifest["ready_for_recording"] else 1
    if args.command == "recheck-discovery":
        from .discovery import recheck_discovery
        from .llm import Planner
        output = RUNS / datetime.now(timezone.utc).strftime("discovery-rechecked-%Y%m%d-%H%M%S-%f")
        report = asyncio.run(recheck_discovery(args.discovery,output,None if args.offline else Planner(settings)))
        print("Status:",report.status)
        print("AI analysis:",report.analysis_status)
        print("Report:",output / "discovery.md")
        return {"complete":0,"partial":1,"failed":2}[report.status]
    if args.command == "plan-demo":
        from .demo_planner import plan_demo
        from .llm import Planner
        output = RUNS / datetime.now(timezone.utc).strftime("demo-plan-%Y%m%d-%H%M%S-%f")
        plan = asyncio.run(plan_demo(args.discovery, output, Planner(settings)))
        print("Scope:", plan.scope)
        print("Flows:", len(plan.flows))
        print("Plan:", output / "demo-plan.json")
        return 0 if plan.flows else 1
    if args.command == "validate-demo":
        from .demo_planner import validate_demo
        output = RUNS / datetime.now(timezone.utc).strftime("demo-validation-%Y%m%d-%H%M%S-%f")
        result = asyncio.run(validate_demo(args.plan, output, args.visible))
        print("Status:", result.status)
        print("Report:", output / "validation.json")
        return 0 if result.status == "passed" else 1
    if args.command == "storyboard":
        if not 20 <= args.duration <= 75:
            parser.error("--duration must be 20-75 seconds")
        from .storyboard import create_storyboard
        from .llm import Planner
        output = RUNS / datetime.now(timezone.utc).strftime("storyboard-%Y%m%d-%H%M%S-%f")
        result = asyncio.run(create_storyboard(args.manifest,output,Planner(settings),args.language,
                                               args.duration,args.aspect_ratio))
        print("Status:",result.status)
        print("Duration:",result.total_duration_seconds)
        print("Scenes:",len(result.scenes))
        print("Storyboard:",output / "storyboard.md")
        return 0 if result.status == "ready" else 1
    if args.command == "record-scenes":
        from .recording import record_storyboard
        output = RUNS / datetime.now(timezone.utc).strftime("recording-%Y%m%d-%H%M%S-%f")
        result = asyncio.run(record_storyboard(args.storyboard,output,args.visible))
        print("Status:",result.status)
        print("Clips:",sum(clip.status=="recorded" for clip in result.clips))
        print("Recording manifest:",output / "recording-manifest.json")
        return 0 if result.status == "ready" else 1
    if args.command == "compose-video":
        from .composer import compose_video
        output = RUNS / datetime.now(timezone.utc).strftime("video-%Y%m%d-%H%M%S-%f")
        result = asyncio.run(compose_video(args.storyboard,args.recording,output,args.voice))
        print("Status:",result.status)
        print("Duration:",result.total_duration_seconds)
        print("Scenes:",len(result.scenes))
        print("Video:",output / result.output_video if result.output_video else "not created")
        print("Manifest:",output / "video-manifest.json")
        return 0 if result.status == "ready" else 1
    if args.command == "package-video":
        from .quality import quality_and_package
        folder,result = quality_and_package(args.video_manifest)
        print("Status:",result.status)
        print("Checks:",sum(check.status=="passed" for check in result.checks),"/",len(result.checks))
        print("QA report:",folder / "qa-report.md")
        print("Archive:",(ROOT/"artifacts"/"exports"/result.archive) if result.archive else "not created")
        return 0 if result.status == "ready" else 1
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        parser.error("Provide an http(s) URL without embedded credentials")
    if not 1 <= args.max_pages <= 20 or not 0 <= args.max_probes <= 20:
        parser.error("--max-pages must be 1-20; --max-probes must be 0-20")
    from .discovery import discover
    from .llm import Planner
    planner = None if args.offline else Planner(settings)
    output = RUNS / datetime.now(timezone.utc).strftime("discovery-%Y%m%d-%H%M%S-%f")
    print("Output:", output, flush=True)
    report = asyncio.run(discover(args.url, output, args.max_pages, args.max_probes, planner, args.visible))
    print("Status:", report.status)
    print("AI analysis:", report.analysis_status)
    print("Pages:", len(report.pages))
    print("Demonstrated interactions:", sum(p.status == "demonstrated" for p in report.probes))
    print("Report:", output / "discovery.md")
    return {"complete":0, "partial":1, "failed":2}[report.status]


def run():
    try:
        return main()
    except Exception as exc:
        message = str(exc)
        for name in ["GOOGLE_API_KEY", "BROWSER_USE_API_KEY", "OPENAI_API_KEY"]:
            import os
            secret = os.getenv(name, "")
            if secret:
                message = message.replace(secret, "[REDACTED]")
        print("Error:", type(exc).__name__, message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
