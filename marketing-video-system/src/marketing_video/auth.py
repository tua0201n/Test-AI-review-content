"""Capture a manually authorized demo session without recording credentials."""
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from .settings import ROOT

AUTH_FILE = ROOT / ".auth" / "state.json"

SAVE_PANEL_SCRIPT = r"""(() => {
    const mount = () => {
        if(window.top!==window || document.getElementById('demo-save-session'))return;
        const box=document.createElement('div');box.id='demo-save-session';
        box.style.cssText='position:fixed;bottom:18px;right:18px;z-index:2147483647;padding:16px;background:#102338;color:white;border-radius:12px;font:14px Arial;box-shadow:0 5px 20px #0005;max-width:390px;pointer-events:auto';
        const text=document.createElement('div');text.id='demo-session-status';
        text.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5';
        text.textContent='Đăng nhập bằng tài khoản demo, sau đó bấm nút bên dưới.';
        const button=document.createElement('button');button.id='demo-session-save';button.type='button';
        button.textContent='Đã đăng nhập — Lưu phiên demo';
        button.style.cssText='margin-top:12px;background:#53e6ae;border:0;padding:12px;border-radius:8px;font-weight:bold;cursor:pointer';
        const close=document.createElement('button');close.id='demo-session-close';close.type='button';
        close.textContent='Đóng cửa sổ';close.hidden=true;
        close.style.cssText='margin-top:12px;margin-left:8px;padding:12px;border:0;border-radius:8px;cursor:pointer';
        button.onclick=async event=>{
            event.preventDefault();event.stopPropagation();
            button.disabled=true;text.textContent='Đang ghi session...';
            try{
                if(typeof window.__saveDemoSession!=='function')throw new Error('Mất kết nối với chương trình login. Hãy chạy lại login.ps1.');
                const result=await window.__saveDemoSession();
                if(!result || typeof result.ok!=='boolean')throw new Error('Phản hồi lưu phiên không hợp lệ. Hãy chạy lại login.ps1.');
                text.textContent=result.message+(result.path?'\n'+result.path:'');
                if(result.ok){button.textContent='Đã lưu thành công';close.hidden=false;}
                else{button.disabled=false;}
            }catch(error){text.textContent='Không lưu được session: '+error.message;button.disabled=false;}
        };
        close.onclick=async()=>{
            try{await window.__finishDemoSession();}
            catch(error){text.textContent='Session đã lưu. Bạn có thể tự đóng cửa sổ này.';}
        };
        box.append(text,button,close);document.body.appendChild(box);
    };
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
})();"""



def session_for(url):
    metadata = AUTH_FILE.parent / "scope.json"
    if not AUTH_FILE.exists() or not metadata.exists():
        return None
    import json
    host = json.loads(metadata.read_text(encoding="utf-8")).get("host")
    return str(AUTH_FILE) if host == urlparse(url).netloc.lower() else None


async def login(url, timeout=600):
    import json
    from datetime import datetime, timezone
    done = asyncio.Event()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width":1280,"height":800})
        page = await context.new_page()

        save_ok = False

        async def save_session():
            nonlocal save_ok
            try:
                if urlparse(page.url).netloc.lower() != urlparse(url).netloc.lower():
                    return {"ok":False,"message":"Hãy trở về website sản phẩm sau khi đăng nhập."}
                if await page.locator('input[type="password"]:visible').count():
                    return {"ok":False,"message":"Bạn vẫn đang ở màn hình đăng nhập. Hãy đăng nhập trước khi lưu."}
                AUTH_FILE.parent.mkdir(parents=True,exist_ok=True)
                state = await asyncio.wait_for(context.storage_state(indexed_db=True),timeout=45)
                host = urlparse(url).hostname.lower()
                def belongs(domain):
                    domain = domain.lstrip(".").lower()
                    return domain == host or domain.endswith("."+host) or host.endswith("."+domain)
                state["cookies"] = [c for c in state["cookies"] if belongs(c["domain"])]
                state["origins"] = [o for o in state["origins"] if belongs(urlparse(o["origin"]).hostname or "")]
                temp = AUTH_FILE.with_suffix(".tmp")
                temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
                temp.replace(AUTH_FILE)
                metadata = AUTH_FILE.parent/"scope.json"
                metadata.write_text(json.dumps({"host":urlparse(url).netloc.lower(),
                    "saved_at":datetime.now(timezone.utc).isoformat(),"landing_url":page.url},indent=2),encoding="utf-8")
                # Confirm both files were written before reporting success.
                json.loads(AUTH_FILE.read_text(encoding="utf-8"))
                json.loads(metadata.read_text(encoding="utf-8"))
                save_ok = True
                print("Demo session saved:",AUTH_FILE,flush=True)
                print("Session metadata:",metadata,flush=True)
                return {"ok":True,"message":"Đã lưu phiên demo thành công.","path":str(AUTH_FILE)}
            except Exception as exc:
                message = "Lỗi lưu phiên: " + type(exc).__name__ + ": " + str(exc)
                print(message,flush=True)
                return {"ok":False,"message":message}

        async def finish_session():
            if save_ok:
                done.set()
                return True
            return False

        await page.expose_function("__saveDemoSession",save_session)
        await page.expose_function("__finishDemoSession",finish_session)
        await page.add_init_script(SAVE_PANEL_SCRIPT)
        try:
            await page.goto(url,wait_until="domcontentloaded",timeout=30000)
            print("Login browser opened. Log in, then click the green Save demo session button.",flush=True)
            try:
                await asyncio.wait_for(done.wait(),timeout=timeout)
            except asyncio.TimeoutError:
                if not save_ok:
                    raise ValueError("Chưa lưu được phiên trong thời gian chờ; hãy chạy lại login.ps1")
            print("Login capture completed:",AUTH_FILE,flush=True)
            return AUTH_FILE
        finally:
            await browser.close()



def import_session_file(source, url):
    """Import an existing Playwright session and bind it to the product host."""
    import json
    from datetime import datetime, timezone
    state = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list) or not isinstance(state.get("origins", []), list):
        raise ValueError("Expected a Playwright storage-state JSON with cookies and origins")
    host = urlparse(url).hostname.lower()
    def belongs(domain):
        domain = domain.lstrip(".").lower()
        return domain == host or domain.endswith("."+host) or host.endswith("."+domain)
    state["cookies"] = [c for c in state["cookies"] if belongs(c.get("domain", ""))]
    state["origins"] = [o for o in state.get("origins", []) if belongs(urlparse(o["origin"]).hostname or "")]
    if not state["cookies"] and not state["origins"]:
        raise ValueError("Session contains no data belonging to the supplied product URL")
    AUTH_FILE.parent.mkdir(exist_ok=True)
    AUTH_FILE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    (AUTH_FILE.parent/"scope.json").write_text(json.dumps({"host":urlparse(url).netloc.lower(),
        "saved_at":datetime.now(timezone.utc).isoformat()},indent=2),encoding="utf-8")
    print("Product session imported; cookie/token values are not displayed.",flush=True)
    return AUTH_FILE
