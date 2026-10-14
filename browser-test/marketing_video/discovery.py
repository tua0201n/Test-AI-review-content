"""Bounded discovery, real interaction probes, and reproducible evidence."""
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urldefrag
from playwright.async_api import async_playwright
from .models import Control, PageEvidence, ExplorationPlan, ProbeRequest, ProbeEvidence, ProductBrief, DiscoveryReport

INVENTORY_JS = r"""() => {
    return [...document.querySelectorAll('a,button,input,select,[role="tab"],[role="button"],summary')]
      .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
      .slice(0,140).map((el,i) => {
        const id = 'c' + i; el.setAttribute('data-mv-id',id);
        const label = el.getAttribute('aria-label') || el.getAttribute('placeholder') ||
          (el.labels && [...el.labels].map(x => x.innerText).join(' ')) || el.innerText || el.name || '';
        return {id,tag:el.tagName.toLowerCase(),label:label.trim().slice(0,250),
          type:el.type || '',href:el.href || '',role:el.getAttribute('role') || '',
          form_submit:el.tagName==='BUTTON' && !!el.form && el.type!=='button',
          options:el.options ? [...el.options].map(x=>x.value) : [],
          expanded:el.getAttribute('aria-expanded'),selected:el.getAttribute('aria-selected')};
      });
}"""
RISK = re.compile(r'\b(delete|remove|buy|purchase|checkout|pay|subscribe|submit|send|apply|logout|sign\s*(in|up|out)|log\s*(in|out)|register|save|create|upload|download)\b|đăng\s*(nhập|ký)|thanh toán|gửi|xóa|xoá|lưu', re.I)
UNSAFE_NAV = re.compile(r'logout|sign[-_]?out|(?:^|[/=])(?:delete|remove|purchase|checkout|unsubscribe)(?:[/?=&_-]|$)', re.I)
SEARCH = re.compile(r'search|tìm\s*kiếm|query|keyword', re.I)
PASSIVE = re.compile(r'filter|sort|next|previous|show|more|less|view|details|faq|menu|play|pause|lọc|sắp xếp|tiếp|trước|chi tiết|xem', re.I)


def same_site(url, root):
    p, r = urlparse(url), urlparse(root)
    return p.scheme in {"http", "https"} and p.netloc.lower() == r.netloc.lower()


def permitted(control, request, root):
    if request.operation == "type":
        if control.tag != "input" or control.type not in {"text", "search", ""} or not SEARCH.search(control.label + " " + control.type):
            return "Only public search fields may be typed into"
        if not request.value.strip() or len(request.value) > 80:
            return "Search query must contain 1-80 characters"
        return None
    if RISK.search(control.label + " " + control.href) or control.form_submit:
        return "Action may submit a form, authenticate, or alter data"
    if request.operation == "select":
        if control.tag != "select" or request.value not in control.options or not PASSIVE.search(control.label):
            return "Only identified filter/sort choices may be selected"
        return None
    if control.tag == "a":
        if not same_site(control.href, root):
            return "Only links on the input website may be followed"
        if urldefrag(control.href)[0] == urldefrag(root)[0] and urlparse(control.href).fragment:
            return "Anchor navigation alone is not a functionality probe"
        return None
    if control.tag == "summary" or control.role == "tab" or control.expanded is not None:
        return None
    if control.tag == "button" or control.role == "button":
        if PASSIVE.search(control.label):
            return None
    return "This control has no established read-only interaction semantics"


def offline_plan(page):
    probes = []
    for c in page.controls:
        if c.tag == "input" and SEARCH.search(c.label + " " + c.type):
            probes.append(ProbeRequest(control_id=c.id, operation="type", value="test", feature="Public search", expected_observation="Visible search results or empty state update"))
        elif c.tag == "summary" or c.expanded is not None or c.role == "tab":
            probes.append(ProbeRequest(control_id=c.id, operation="click", feature=c.label or "Disclosure/tab", expected_observation="Content visibility or selection changes"))
    urls = list(dict.fromkeys(c.href for c in page.controls if c.tag == "a" and c.href and not urlparse(c.href).fragment))
    return ExplorationPlan(page_purpose=page.title, probes=probes[:2], priority_urls=urls[:8])


def assess_changes(before, after, old_state, new_state):
    changes = []
    if before.url != after.url:
        changes.append("URL changed: " + after.url)
    if old_state.get("expanded") != new_state.get("expanded"):
        changes.append("Disclosure expanded state changed")
    if old_state.get("selected") != new_state.get("selected"):
        changes.append("Tab selection changed")
    # Input value changing alone is not proof that search actually worked.
    b = before.text.strip()
    a = after.text.strip()
    old_value, new_value = old_state.get("value", ""), new_state.get("value", "")
    if old_value:
        b = b.replace(old_value, "")
    if new_value:
        a = a.replace(new_value, "")
    if b != a:
        changes.append("Visible page content changed")
    return changes


async def snapshot(page, folder, evidence_id):
    await page.wait_for_timeout(700)
    controls = [Control.model_validate(x) for x in await page.evaluate(INVENTORY_JS)]
    text = (await page.locator("body").inner_text())[:24000]
    screenshot = "screenshots/" + evidence_id + ".png"
    await page.screenshot(path=str(folder / screenshot), full_page=False)
    path = urlparse(page.url).path.lower()
    gated = bool(any(c.type == "password" for c in controls) and (re.search(r'login|signin|sign-in|signup|register', path) or len(controls) < 25))
    return PageEvidence(id=evidence_id, url=page.url, title=await page.title(), text=text,
                        screenshot=screenshot, controls=controls, requires_auth=gated)


async def target_state(locator):
    return await locator.evaluate("el => ({value:el.value || '',expanded:el.getAttribute('aria-expanded'),selected:el.getAttribute('aria-selected')})")


async def probe(page, initial, request, folder, probe_id, root):
    expected = next((c for c in initial.controls if c.id == request.control_id), None)
    if expected is None:
        return ProbeEvidence(id=probe_id, page_id=initial.id, request=request, status="blocked_action",
                             before=initial, reason="Model referenced an unknown control ID")
    reason = permitted(expected, request, root)
    if reason or initial.requires_auth:
        return ProbeEvidence(id=probe_id, page_id=initial.id, request=request,
            status="blocked_auth" if initial.requires_auth else "blocked_action", before=initial,
            reason="Requires an authenticated session" if initial.requires_auth else reason)
    before = initial
    after = None
    replay = ""
    try:
        await page.goto(initial.url, wait_until="domcontentloaded", timeout=30000)
        await settle(page)
        before = await snapshot(page, folder, probe_id + "-before")
        fresh = next((c for c in before.controls if (c.tag,c.label,c.href,c.type) == (expected.tag,expected.label,expected.href,expected.type)), None)
        if fresh is None:
            raise ValueError("Target changed since planning; refusing to act on a different control")
        locator = page.locator('[data-mv-id="' + fresh.id + '"]')
        replay = json.dumps({"tag":fresh.tag,"label":fresh.label,"href":fresh.href,"type":fresh.type}, ensure_ascii=False)
        old = await target_state(locator)
        if request.operation == "type":
            await locator.fill(request.value)
        elif request.operation == "select":
            await locator.select_option(request.value)
        else:
            await locator.click(timeout=10000)
        await settle(page)
        after = await snapshot(page, folder, probe_id + "-after")
        new = await target_state(locator) if await locator.count() and before.url == after.url else {}
        changes = assess_changes(before, after, old, new)
        if after.requires_auth:
            status, reason = "blocked_auth", "Interaction leads to an authentication screen"
        elif changes:
            status, reason = "demonstrated", "; ".join(changes)
        else:
            status, reason = "no_observable_result", "No visible result changed; typing into a search field alone does not verify search"
        return ProbeEvidence(id=probe_id, page_id=initial.id, request=request, status=status,
                             before=before, after=after, observed_changes=changes, reason=reason, target_fingerprint=replay)
    except Exception as exc:
        return ProbeEvidence(id=probe_id, page_id=initial.id, request=request, status="failed", before=before,
                             after=after, reason=type(exc).__name__ + ": " + str(exc)[:500], target_fingerprint=replay)


async def settle(page):
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    await page.wait_for_timeout(900)


def validate_brief(brief, report):
    page_ids = {p.id for p in report.pages}
    allowed = {p.id for p in report.probes if p.status == "demonstrated"}
    for claim in brief.advertised_features:
        if not claim.source_page_ids or not set(claim.source_page_ids) <= page_ids:
            raise ValueError("Product claim contains a missing or unknown source page")
    if not set(brief.recommended_demo_probe_ids) <= allowed:
        raise ValueError("Brief recommends a probe without demonstrated evidence")
    return brief


def markdown_report(report):
    lines = ["# Website discovery", "", "URL: " + report.input_url,
             "Mode: " + report.mode + " | Status: " + report.status,
             "AI analysis: " + report.analysis_status, ""]
    if report.brief:
        lines += ["## Product brief", "", report.brief.product_name, report.brief.positioning, "",
                  "Advertised descriptions (not proof of functional behavior):"]
        lines += ["- " + c.description + " [" + ", ".join(c.source_page_ids) + "]" for c in report.brief.advertised_features]
    lines += ["", "## Real interactions", "", "| Probe | Function | Result | Observation |", "|---|---|---|---|"]
    lines += ["| " + p.id + " | " + p.request.feature.replace("|", "/") + " | " + p.status + " | " + p.reason.replace("|", "/").replace("\n", " ") + " |" for p in report.probes]
    lines += ["", "## Pages", ""]
    lines += ["- " + p.id + ": " + p.url + (" (authentication required)" if p.requires_auth else "") for p in report.pages]
    if report.errors:
        lines += ["", "## Errors", ""] + ["- " + e for e in report.errors]
    if report.brief and report.brief.limitations:
        lines += ["", "## Limitations", ""] + ["- " + x for x in report.brief.limitations]
    return "\n".join(lines) + "\n"


async def discover(url, folder, max_pages=6, max_probes=6, planner=None, visible=False):
    report = DiscoveryReport(input_url=url, started_at=datetime.now(timezone.utc).isoformat(),
                             mode="llm" if planner else "offline", model=planner.model if planner else None,
                             analysis_status="pending" if planner else "not_requested")
    (folder / "screenshots").mkdir(parents=True)
    pending = [url]
    visited = set()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not visible)
        context = await browser.new_context(viewport={"width":1280,"height":720}, accept_downloads=False)
        page = await context.new_page()
        root = url
        try:
            while pending and len(report.pages) < max_pages:
                candidate = pending.pop(0)
                key = urldefrag(candidate)[0].rstrip("/")
                if key in visited:
                    continue
                visited.add(key)
                try:
                    print("Page:", candidate, flush=True)
                    await page.goto(candidate, wait_until="domcontentloaded", timeout=30000)
                    await settle(page)
                    if not report.pages:
                        root = page.url
                    if not same_site(page.url, root):
                        raise ValueError("Navigation redirected outside the input website")
                    ev = await snapshot(page, folder, "page-" + str(len(report.pages)+1).zfill(2))
                    report.pages.append(ev)
                    if planner:
                        try:
                            plan = await planner.plan(ev)
                        except Exception as exc:
                            report.errors.append("LLM planning unavailable: " + type(exc).__name__ + ": " + str(exc)[:700])
                            report.status = "partial"
                            report.analysis_status = "unavailable"
                            planner = None  # Continue browser evidence, without repeated failing API calls.
                            plan = offline_plan(ev)
                    else:
                        plan = offline_plan(ev)
                    (folder / (ev.id + "-plan.json")).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
                    known = {c.href for c in ev.controls if c.tag == "a"}
                    priorities = [x for x in plan.priority_urls if x in known and same_site(x, root)]
                    others = [x for x in known if same_site(x, root) and not urlparse(x).fragment]
                    others.sort(key=lambda x: (bool(re.search('privacy|terms|deletion', x)), x))
                    for link in priorities + others:
                        if UNSAFE_NAV.search(link):
                            continue
                        if urldefrag(link)[0].rstrip("/") not in visited and link not in pending:
                            pending.append(link)
                    for req in plan.probes[:2]:
                        if len(report.probes) >= max_probes:
                            break
                        pid = "probe-" + str(len(report.probes)+1).zfill(2)
                        result = await probe(page, ev, req, folder, pid, root)
                        report.probes.append(result)
                        print("Probe:", pid, req.feature, result.status, flush=True)
                except Exception as exc:
                    report.errors.append(candidate + ": " + type(exc).__name__ + ": " + str(exc)[:700])
                    report.status = "partial"
                finally:
                    save_report(report, folder)
        finally:
            await context.close()
            await browser.close()
    if not report.pages:
        report.status = "failed"
    elif planner:
        try:
            report.brief = validate_brief(await planner.brief(report), report)
            report.analysis_status = "complete"
        except Exception as exc:
            report.status = "partial"
            report.analysis_status = "unavailable"
            report.errors.append("Product brief: " + type(exc).__name__ + ": " + str(exc)[:700])
    save_report(report, folder)
    return report


def save_report(report, folder):
    (folder / "discovery.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    (folder / "discovery.md").write_text(markdown_report(report), encoding="utf-8")
