"""Run a configurable Browser Use model test and save its result."""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
os.environ.setdefault("BROWSER_USE_CONFIG_DIR", str(ROOT / ".browser-use"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / ".cache"))
from browser_use import Agent, Browser, ChatBrowserUse, ChatOpenAI


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check dependencies and configuration without calling a model")
    parser.add_argument("--smoke", action="store_true", help="Launch a local browser without calling a model")
    parser.add_argument("--task", default="""Review https://aisoeasy.co/ for a Vietnamese marketing demo.
Explore the homepage and use the visible Product, Individuals, Learning Paths and Pricing navigation.
Open Browse all jobs, try searching for Marketing and report the actual result including an empty state.
Inspect the signup and login screens without submitting or entering credentials.
If already authenticated, demonstrate accessible learning and dashboard features using read-only actions.
Do not create accounts, apply for jobs, send forms, make payments or alter stored data.
Distinguish demonstrated functionality from promotional descriptions on the homepage.
Finish in Vietnamese with: actions performed, observations, blocked features, and a 60-90 second
marketing narration based only on observed facts. Do not claim untested functionality works.""")
    parser.add_argument("--max-steps", type=int, default=35)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--login", action="store_true", help="Open a browser for manual login and save local session state")
    parser.add_argument("--no-video", action="store_true", help="Disable MP4 session recording")
    return parser.parse_args()


async def main(args):
    from importlib.metadata import version
    from playwright.async_api import async_playwright
    provider = os.getenv("MODEL_PROVIDER", "browser-use").strip().lower()
    model = os.getenv("MODEL_NAME", "").strip()
    key_name = "BROWSER_USE_API_KEY" if provider == "browser-use" else "OPENAI_API_KEY"
    if provider not in {"browser-use", "openai"}:
        raise ValueError("MODEL_PROVIDER must be browser-use or openai")
    async with async_playwright() as pw:
        executable = pw.chromium.executable_path
        if args.login:
            login_browser = await pw.chromium.launch(headless=False)
            context = await login_browser.new_context(viewport={"width": 1280, "height": 720})
            try:
                page = await context.new_page()
                await page.goto("https://aisoeasy.co/login", wait_until="domcontentloaded")
                await asyncio.to_thread(input, "Log in in the browser. Once you see the authenticated app, press Enter here to save the session: ")
                auth_dir = ROOT / ".auth"
                auth_dir.mkdir(exist_ok=True)
                await context.storage_state(path=str(auth_dir / "state.json"))
                print("Local session saved. Run run.ps1 to test the authenticated website.")
            finally:
                await login_browser.close()
            return 0
        if args.smoke:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content("<title>Browser test OK</title><h1>Ready</h1>")
                assert await page.title() == "Browser test OK"
                print("Chromium smoke test: OK")
            finally:
                await browser.close()
            session = Browser(headless=True, executable_path=executable, enable_default_extensions=False)
            try:
                await session.start()
                print("Browser Use CDP: OK")
            finally:
                await session.kill()
            return 0
    if args.check:
        print("Python:", sys.version.split()[0])
        print("browser-use:", version("browser-use"))
        print("Provider:", provider)
        print("Model:", model or "ChatBrowserUse default")
        print("Chromium:", "OK" if Path(executable).exists() else "MISSING - run setup.ps1")
        print(key_name + ":", "configured" if os.getenv(key_name) else "missing - edit .env")
        return 0 if Path(executable).exists() else 1
    if args.max_steps < 1:
        raise ValueError("--max-steps must be positive")
    if not os.getenv(key_name):
        raise ValueError(f"Missing {key_name}. Add it to {ROOT / '.env'}")
    if provider == "openai":
        if not model:
            raise ValueError("Set MODEL_NAME for the OpenAI-compatible provider")
        llm = ChatOpenAI(model=model, api_key=os.environ[key_name], base_url=os.getenv("OPENAI_BASE_URL") or None)
    else:
        llm = ChatBrowserUse(**({"model": model} if model else {}))
    output = ROOT / "results" / datetime.now(timezone.utc).strftime("review-%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / ".auth" / "state.json"
    browser = Browser(
        storage_state=state_path if state_path.exists() else None,
        headless=args.headless, executable_path=executable,
        window_size={"width": 1280, "height": 720}, viewport={"width": 1280, "height": 720},
        highlight_elements=False, dom_highlight_elements=False,
        record_video_dir=output / "video" if not args.no_video else None,
        record_video_size={"width": 1280, "height": 720}, record_video_framerate=24,
    )
    print("Review output:", output)
    try:
        agent = Agent(task=args.task, llm=llm, browser=browser)
        history = await agent.run(max_steps=args.max_steps)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        result = {"provider": provider, "model": model or "ChatBrowserUse default", "task": args.task,
                  "success": history.is_successful(), "steps": history.number_of_steps(),
                  "result": history.final_result(), "errors": history.errors()}
        target = output / f"run-{stamp}.json"
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (output / "review-script.txt").write_text(history.final_result() or "No final review returned.", encoding="utf-8")
        print(history.final_result())
        print("Saved:", target)
        return 0 if history.is_successful() else 1
    finally:
        await browser.kill()
        videos = list((output / "video").glob("*.mp4"))
        for video in videos:
            print("Session video:", video)
        if not args.no_video and not videos:
            print("No video produced: check browser/CDP startup and recording logs.", file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(parse_args())))
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
