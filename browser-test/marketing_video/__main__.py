"""CLI for the first URL-to-video pipeline stage."""
import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))


def main():
    parser = argparse.ArgumentParser(description="Research a website for an evidence-based marketing demo")
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("discover")
    research.add_argument("url")
    research.add_argument("--max-pages", type=int, default=6)
    research.add_argument("--max-probes", type=int, default=6)
    research.add_argument("--offline", action="store_true", help="Collect browser evidence without calling a model")
    research.add_argument("--visible", action="store_true")
    args = parser.parse_args()
    parsed = urlparse(args.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        parser.error("Provide an http(s) URL without embedded credentials")
    if not 1 <= args.max_pages <= 20 or not 0 <= args.max_probes <= 20:
        parser.error("--max-pages must be 1-20; --max-probes must be 0-20")
    from .discovery import discover
    from .llm import Planner
    planner = None if args.offline else Planner()
    output = ROOT / "results" / datetime.now(timezone.utc).strftime("discovery-%Y%m%d-%H%M%S-%f")
    print("Output:", output, flush=True)
    report = asyncio.run(discover(args.url, output, args.max_pages, args.max_probes, planner, args.visible))
    print("Status:", report.status)
    print("Pages:", len(report.pages))
    print("Demonstrated interactions:", sum(p.status == "demonstrated" for p in report.probes))
    print("Report:", output / "discovery.md")
    return {"complete":0, "partial":1, "failed":2}[report.status]


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print("Error:", exc)
        raise SystemExit(2)
