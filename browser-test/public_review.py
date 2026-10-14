"""Record a captioned public website tour without an LLM or account."""
import argparse
import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
from playwright.async_api import async_playwright
import imageio_ffmpeg

SCENES = [
    ("home", "AI So Easy | Nâng cấp kỹ năng AI", "Khám phá nền tảng học kỹ năng AI dành cho cá nhân và đội ngũ.", 8),
    ("product", "Một nơi để khám phá các giải pháp", "Trang sản phẩm giới thiệu học liệu AI, chương trình kỹ năng và dashboard đội ngũ.", 10),
    ("paths", "Lộ trình theo công việc", "Xem gợi ý lộ trình cho Sales, Marketing, Finance, HR và Operations.", 10),
    ("individual", "Từ học đến thực hành", "Website giới thiệu hành trình học, thực hành, đánh giá và chứng nhận.", 9),
    ("jobs", "Khám phá cơ hội nghề nghiệp", "Mở bảng việc làm và thử tìm kiếm theo vị trí Marketing.", 10),
    ("pricing", "So sánh các gói sử dụng", "Xem thông tin các gói Free, Pro và Business trực tiếp trên website.", 10),
    ("signup", "Bắt đầu với tài khoản của bạn", "Khám phá màn hình đăng ký; trải nghiệm bên trong cần tài khoản.", 9),
    ("login", "Sẵn sàng trải nghiệm sâu hơn?", "Đăng nhập để kiểm tra các chức năng học tập và dashboard thực tế.", 8),
    ("cta", "Khám phá tại aisoeasy.co", "Chọn lộ trình phù hợp và bắt đầu tìm hiểu AI So Easy ngay hôm nay.", 7),
]

PRESENTER_JS = r"""
(() => {
    const mount = () => {
        if (document.getElementById('review-cursor')) return;
        const style = document.createElement('style');
        style.textContent = 'html{scroll-behavior:smooth!important}body,body *{cursor:none!important}#review-cursor{position:fixed;left:90px;top:110px;width:32px;height:40px;z-index:2147483647;pointer-events:none;filter:drop-shadow(0 3px 3px #0009)}#review-cursor svg{transform-origin:3px 2px;transition:transform .12s}#review-cursor[data-down] svg{transform:scale(.82)}.review-ripple{position:fixed;width:16px;height:16px;border:3px solid #53e6ae;border-radius:50%;background:#53e6ae44;pointer-events:none;z-index:2147483646;animation:review-click .65s ease-out forwards}@keyframes review-click{from{transform:translate(-50%,-50%) scale(.5);opacity:1}to{transform:translate(-50%,-50%) scale(4);opacity:0}}';
        document.head.appendChild(style);
        const cursor = document.createElement('div'); cursor.id = 'review-cursor';
        cursor.innerHTML = '<svg width="32" height="40" viewBox="0 0 32 40"><path d="M3 2 L3 30 L10 24 L16 37 L22 34 L16 22 L27 22 Z" fill="white" stroke="#102338" stroke-width="2" stroke-linejoin="round"/></svg>';
        document.body.appendChild(cursor);
        window.__reviewCursor = (x,y) => {cursor.style.left=x+'px';cursor.style.top=y+'px';};
        document.addEventListener('mousemove',e=>window.__reviewCursor(e.clientX,e.clientY),true);
        document.addEventListener('mousedown',e=>{
            cursor.setAttribute('data-down','');
            const ring=document.createElement('div');ring.className='review-ripple';
            ring.style.left=e.clientX+'px';ring.style.top=e.clientY+'px';
            document.body.appendChild(ring);setTimeout(()=>ring.remove(),750);
        },true);
        document.addEventListener('mouseup',()=>cursor.removeAttribute('data-down'),true);
    };
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();
"""


class Presenter:
    """Real pointer actions with an on-screen cursor and click feedback."""
    def __init__(self, page):
        self.page = page
        self.x, self.y = 90.0, 110.0
        self.actions = []

    async def restore(self):
        await self.page.wait_for_function("typeof window.__reviewCursor === 'function'")
        await self.page.evaluate("([x,y]) => window.__reviewCursor(x,y)", [self.x, self.y])

    async def move(self, x, y, seconds=0.75):
        sx, sy = self.x, self.y
        steps = 30
        for i in range(1, steps + 1):
            t = i / steps
            ease = t * t * (3 - 2 * t)
            arc = 24 * 4 * t * (1 - t)
            await self.page.mouse.move(sx + (x-sx)*ease, sy + (y-sy)*ease + arc)
            await self.page.wait_for_timeout(seconds * 1000 / steps)
        self.x, self.y = x, y

    async def point(self, locator, click=False):
        locator = locator.first
        await locator.wait_for(state="visible")
        await locator.scroll_into_view_if_needed()
        await self.page.wait_for_timeout(450)
        box = await locator.bounding_box()
        if not box:
            raise RuntimeError("Could not locate presentation target")
        label = (await locator.inner_text())[:120] or await locator.get_attribute("placeholder") or "control"
        await self.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await locator.evaluate("el => el.animate([{boxShadow:'0 0 0 0 #53e6ae00'},{boxShadow:'0 0 0 4px #53e6ae88'},{boxShadow:'0 0 0 0 #53e6ae00'}],{duration:900})")
        await self.page.wait_for_timeout(350)
        self.actions.append({"action": "click" if click else "hover", "label": label, "url": self.page.url})
        if click:
            await locator.click(trial=True)
            await self.page.mouse.down()
            await self.page.wait_for_timeout(140)
            await self.page.mouse.up()
            await self.page.wait_for_timeout(650)

    async def click(self, locator):
        await self.point(locator, click=True)
        await self.page.wait_for_load_state("domcontentloaded")
        await self.restore()

    async def park(self):
        await self.move(1195, 475, seconds=0.5)


async def caption(page, title, detail):
    await page.evaluate("""([title, detail]) => {
        let box = document.getElementById('review-caption');
        if (!box) {
            box = document.createElement('div'); box.id = 'review-caption';
            box.style.cssText = 'position:fixed;z-index:2147483647;bottom:18px;left:24px;right:24px;padding:18px 24px;background:rgba(11,20,39,.94);color:white;border-left:5px solid #53e6ae;border-radius:12px;font-family:Arial,sans-serif;pointer-events:none;box-shadow:0 5px 24px #0004';
            document.body.appendChild(box);
        }
        box.replaceChildren();
        const label = document.createElement('div'); label.textContent = 'AI SO EASY · DEMO WEBSITE CÔNG KHAI';
        label.style.cssText = 'font-size:11px;letter-spacing:2px;color:#53e6ae;margin-bottom:7px';
        const heading = document.createElement('div'); heading.textContent = title;
        heading.style.cssText = 'font-size:24px;font-weight:700;margin-bottom:7px';
        const body = document.createElement('div'); body.textContent = detail;
        body.style.cssText = 'font-size:17px;line-height:1.45';
        box.append(label, heading, body);
        box.animate([{opacity:0,transform:"translateY(14px)"},{opacity:1,transform:"translateY(0)"}],{duration:500,easing:"ease-out"});
    }""", [title, detail])


async def record(args):
    output = ROOT / "results" / datetime.now(timezone.utc).strftime("public-review-%Y%m%d-%H%M%S-%f")
    output.mkdir(parents=True)
    observations = []
    print("Output:", output, flush=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not args.visible)
        context = await browser.new_context(viewport={"width": 1280, "height": 720},
            record_video_dir=str(output / "raw"), record_video_size={"width": 1280, "height": 720})
        await context.add_init_script(PRESENTER_JS)
        page = await context.new_page()
        presenter = Presenter(page)
        video = page.video
        try:
            await page.goto("https://aisoeasy.co/", wait_until="networkidle", timeout=60000)
            for key, title, detail, duration in SCENES:
                print("Scene:", key, flush=True)
                if key in {"product", "paths", "individual", "pricing"}:
                    if not page.url.startswith("https://aisoeasy.co/#") and page.url.rstrip("/") != "https://aisoeasy.co":
                        await page.goto("https://aisoeasy.co/", wait_until="networkidle")
                    await presenter.click(page.locator('a[href="#' + key + '"]'))
                elif key == "jobs":
                    await presenter.click(page.locator('a[href="/jobs"]'))
                    await page.wait_for_load_state("networkidle")
                    search = page.get_by_placeholder("Search job title…")
                    await presenter.click(search)
                    await search.press_sequentially("Marketing", delay=140)
                    await page.wait_for_timeout(500)
                    text = await page.locator("body").inner_text()
                    if "No openings right now" in text:
                        detail = "Tìm kiếm Marketing: hiện bảng việc làm chưa có vị trí đang mở."
                elif key == "signup":
                    await presenter.click(page.locator('a[href="/signup"]'))
                    await page.wait_for_load_state("networkidle")
                elif key == "login":
                    await presenter.click(page.locator('a[href="/login"]'))
                    await page.wait_for_load_state("networkidle")
                elif key == "cta":
                    await page.goto("https://aisoeasy.co/", wait_until="networkidle")
                await presenter.restore()
                await page.wait_for_timeout(700)
                await caption(page, title, detail)
                if key == "product":
                    await presenter.point(page.get_by_text("AI Learning Hub", exact=True))
                    await presenter.point(page.get_by_text("Skill Upgrade Programs", exact=True))
                elif key == "paths":
                    await presenter.point(page.get_by_text("Create more content in less time", exact=True))
                elif key == "signup":
                    await presenter.click(page.get_by_placeholder("you@company.com"))
                elif key == "login":
                    await presenter.click(page.get_by_placeholder("Employee ID / Email / Phone"))
                elif key == "cta":
                    await presenter.point(page.locator('a[href="/signup"]'))
                await presenter.park()
                observations.append({"scene": key, "url": page.url, "title": title, "narration": detail,
                    "suggested_seconds": duration, "page_text": (await page.locator("body").inner_text())[:20000]})
                await page.screenshot(path=str(output / (key + ".png")))
                await page.wait_for_timeout(int(duration * args.pace * 1000))
        finally:
            await context.close()
            await browser.close()
            (output / "actions.json").write_text(json.dumps(presenter.actions, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "observations.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")
            (output / "voiceover-vi.txt").write_text("\n\n".join(x["narration"] for x in observations), encoding="utf-8")
        raw = await video.path()
    target = output / "review-marketing.mp4"
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    import imageio.v2 as iio
    reader = iio.get_reader(raw)
    raw_duration = reader.get_meta_data()["duration"]
    reader.close()
    speed = min(1.0, 90 * args.pace / raw_duration)
    subprocess.run([ffmpeg, "-y", "-i", raw, "-vf", f"setpts={speed:.6f}*PTS", "-r", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "20", "-movflags", "+faststart", str(target)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print("Video:", target, flush=True)
    print("Vietnamese voiceover script:", output / "voiceover-vi.txt", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--pace", type=float, default=1.0, help="Scene duration multiplier")
    args = parser.parse_args()
    if args.pace <= 0:
        parser.error("--pace must be positive")
    asyncio.run(record(args))
