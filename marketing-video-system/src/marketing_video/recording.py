"""Record verified demo scenes with a rendered cursor and reproducible traces."""
import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path
from playwright.async_api import async_playwright
from .auth import session_for
from .demo_planner import check_point, find_control, LOADING
from .discovery import permitted, same_site, settle, snapshot, target_state
from .models import (ActionTrace, DemoPlan, DemoValidation, ProbeRequest, RecordedClip,
                     RecordingManifest, Storyboard)

VIEWPORT = {"width": 1280, "height": 720}

CURSOR_SETUP = r"""() => {
  if (window.__mvCursor) return;
  const style = document.createElement('style');
  style.id = 'mv-cursor-style';
  style.textContent = `html,body,body *{cursor:none!important}
    #mv-cursor{position:fixed;z-index:2147483647;left:0;top:0;width:30px;height:38px;
      pointer-events:none;filter:drop-shadow(0 2px 2px rgba(0,0,0,.5));transform:translate(-3px,-2px)}
    #mv-click{position:fixed;z-index:2147483646;width:18px;height:18px;border:3px solid #35e0a1;
      border-radius:50%;pointer-events:none;opacity:0;transform:translate(-50%,-50%) scale(.35)}
    #mv-click.pulse{animation:mv-pulse .55s ease-out}
    @keyframes mv-pulse{0%{opacity:1;transform:translate(-50%,-50%) scale(.35)}100%{opacity:0;transform:translate(-50%,-50%) scale(2.5)}}`;
  document.documentElement.appendChild(style);
  const cursor = document.createElement('div'); cursor.id='mv-cursor';
  cursor.innerHTML='<svg width="30" height="38" viewBox="0 0 30 38"><path d="M3 2 L25 22 L15 23 L21 35 L15 38 L9 25 L3 32 Z" fill="white" stroke="#111" stroke-width="2" stroke-linejoin="round"/></svg>';
  const click = document.createElement('div'); click.id='mv-click';
  document.documentElement.append(cursor,click);
  let x=Math.round(innerWidth*.12), y=Math.round(innerHeight*.78);
  const draw=()=>{cursor.style.left=x+'px';cursor.style.top=y+'px'}; draw();
  window.__mvCursor={
    position:()=>({x,y}),
    moveTo:(tx,ty,duration=900)=>new Promise(resolve=>{
      const sx=x,sy=y,start=performance.now();
      const tick=now=>{const p=Math.min(1,(now-start)/duration);const e=1-Math.pow(1-p,3);
        x=sx+(tx-sx)*e;y=sy+(ty-sy)*e;draw();if(p<1)requestAnimationFrame(tick);else resolve();};
      requestAnimationFrame(tick);
    }),
    pulse:()=>new Promise(resolve=>{click.style.left=x+'px';click.style.top=y+'px';click.classList.remove('pulse');
      void click.offsetWidth;click.classList.add('pulse');setTimeout(resolve,280);})
  };
}"""


def _inside(root, value, label):
    root = Path(root).resolve()
    path = Path(value).resolve() if Path(value).is_absolute() else (root / value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(label + " must be an existing file inside the storyboard run folder")
    return path


def load_recording_sources(storyboard_path):
    storyboard_path = Path(storyboard_path).resolve()
    storyboard = Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))
    if storyboard.status != "ready" or not storyboard.review.approved or storyboard.review.unsupported_scene_ids:
        raise ValueError("Storyboard is not approved and ready")
    plan_path = Path(storyboard.source_plan).resolve()
    validation_path = Path(storyboard.source_validation).resolve()
    if not plan_path.is_file() or not validation_path.is_file():
        raise ValueError("Storyboard source plan or validation is missing")
    plan = DemoPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    validation = DemoValidation.model_validate_json(validation_path.read_text(encoding="utf-8"))
    if validation.status != "passed" or Path(validation.source_plan).resolve() != plan_path:
        raise ValueError("Storyboard does not reference a passed Task 2 validation")
    passed = {flow.flow_id for flow in validation.flows if flow.status == "passed"}
    flows = {flow.id:flow for flow in plan.flows if flow.id in passed}
    demo_scenes = [scene for scene in storyboard.scenes if scene.scene_type == "demo"]
    if not demo_scenes:
        raise ValueError("Storyboard has no demo scenes to record")
    for scene in demo_scenes:
        flow = flows.get(scene.flow_id)
        if not flow or scene.step_index < 1 or scene.step_index >= len(flow.steps):
            raise ValueError("Storyboard demo scene references an unavailable passed step: " + scene.id)
        if f"step:{scene.flow_id}:{scene.step_index}" not in scene.evidence_ids:
            raise ValueError("Storyboard demo scene does not cite its exact step: " + scene.id)
    return storyboard_path, storyboard, plan_path, validation_path, plan, validation


async def _cursor_to(page, locator):
    await page.evaluate(CURSOR_SETUP)
    await locator.scroll_into_view_if_needed(timeout=10000)
    box = await locator.bounding_box()
    if not box:
        raise ValueError("Target has no visible bounding box")
    origin = await page.evaluate("() => window.__mvCursor.position()")
    destination = {"x":box["x"]+box["width"]/2,"y":box["y"]+box["height"]/2}
    await page.evaluate("p => window.__mvCursor.moveTo(p.x,p.y,p.duration)",
                        {**destination,"duration":1000})
    return [round(origin["x"],1),round(origin["y"],1)], [round(destination["x"],1),round(destination["y"],1)]


async def _perform(page, locator, step):
    await page.evaluate("() => window.__mvCursor.pulse()")
    if step.operation == "click":
        await locator.click(timeout=10000)
    elif step.operation == "type":
        await locator.click(timeout=10000)
        await locator.fill("")
        await locator.press_sequentially(step.value,delay=70)
    elif step.operation == "select":
        await locator.select_option(step.value)
    else:
        raise ValueError("Unsupported recording operation: "+step.operation)


def _ffmpeg_executable():
    configured = shutil.which("ffmpeg")
    if configured:
        return configured
    from .settings import RUNTIME
    bundled = sorted((RUNTIME/"browsers").glob("ffmpeg-*/ffmpeg-win64.exe"),reverse=True)
    if bundled:
        return str(bundled[0])
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("FFmpeg is required to split recorded scenes") from exc


def _split_clip(ffmpeg, source, target, start, duration):
    command=[ffmpeg,"-y","-loglevel","error","-ss",f"{max(0,start):.3f}","-i",str(source),
             "-t",f"{duration:.3f}","-an","-c:v","libvpx","-deadline","realtime","-cpu-used","8",str(target)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=120)
    if result.returncode:
        raise RuntimeError("FFmpeg clip failed: "+result.stderr[-500:])


async def record_storyboard(storyboard_path, folder, visible=False):
    (storyboard_path, storyboard, plan_path, validation_path,
     plan, validation) = load_recording_sources(storyboard_path)
    folder=Path(folder).resolve()
    for name in ["raw","clips","posters","screenshots"]:
        (folder/name).mkdir(parents=True,exist_ok=True)
    scene_by_step={(scene.flow_id,scene.step_index):scene for scene in storyboard.scenes if scene.scene_type=="demo"}
    selected_flow_ids=list(dict.fromkeys(scene.flow_id for scene in storyboard.scenes if scene.scene_type=="demo"))
    flows={flow.id:flow for flow in plan.flows}
    clips=[]
    errors=[]
    ffmpeg=_ffmpeg_executable()
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=not visible)
        try:
            for flow_id in selected_flow_ids:
                flow=flows[flow_id]
                context=await browser.new_context(viewport=VIEWPORT,accept_downloads=False,
                    storage_state=session_for(plan.site_url or plan.input_url),record_video_dir=str(folder/"raw"),
                    record_video_size=VIEWPORT)
                await context.add_init_script(script="("+CURSOR_SETUP+")()")
                page=await context.new_page()
                video=page.video
                base=time.perf_counter()
                flow_clips=[]
                try:
                    await page.goto(flow.initial_url,wait_until="domcontentloaded",timeout=30000)
                    await settle(page)
                    if not same_site(page.url,plan.site_url or plan.input_url):
                        raise ValueError("Initial recording navigation left the product site")
                    await page.evaluate(CURSOR_SETUP)
                    for index,step in enumerate(flow.steps):
                        if step.operation=="navigate":
                            continue
                        scene=scene_by_step.get((flow_id,index))
                        if scene is None:
                            raise ValueError(f"No storyboard scene for {flow_id} step {index}")
                        before=await snapshot(page,folder,f"{scene.id}-before")
                        if before.requires_auth:
                            raise ValueError("Recording reached an authentication gate")
                        control=find_control(before,step.target)
                        if control is None:
                            raise ValueError("Verified target is missing or ambiguous: "+scene.id)
                        request=ProbeRequest(control_id=control.id,operation=step.operation,value=step.value,
                            feature=flow.title,expected_observation="Recorded Task 2 checkpoint")
                        reason=permitted(control,request,plan.site_url or plan.input_url)
                        if reason:
                            raise ValueError(reason)
                        locator=page.locator('[data-mv-id="'+control.id+'"]')
                        scene_start=time.perf_counter()
                        start_seconds=scene_start-base
                        cursor_from,cursor_to=await _cursor_to(page,locator)
                        old_url=page.url
                        await _perform(page,locator,step)
                        await settle(page)
                        state=await target_state(locator) if await locator.count() and page.url==old_url else {}
                        after=await snapshot(page,folder,f"{scene.id}-after")
                        if not same_site(after.url,plan.site_url or plan.input_url) or after.requires_auth or LOADING.search(after.text):
                            raise ValueError("Recorded action did not reach a usable same-site result")
                        checks=[check_point(point,after,state,index) for point in step.checkpoints]
                        if not checks or any(not check.passed for check in checks):
                            raise ValueError("Recording checkpoint mismatch: "+scene.id)
                        elapsed=time.perf_counter()-scene_start
                        if elapsed < scene.duration_seconds:
                            await page.wait_for_timeout(round((scene.duration_seconds-elapsed)*1000))
                        end_seconds=time.perf_counter()-base
                        poster_rel="posters/"+scene.id+".png"
                        await page.screenshot(path=str(folder/poster_rel),full_page=False)
                        trace=ActionTrace(scene_id=scene.id,flow_id=flow_id,step_index=index,
                            operation=step.operation,target_label=control.label,value=step.value,
                            started_seconds=round(start_seconds,3),ended_seconds=round(end_seconds,3),
                            cursor_from=cursor_from,cursor_to=cursor_to,checkpoints=checks)
                        clip=RecordedClip(scene_id=scene.id,flow_id=flow_id,step_index=index,status="recorded",
                            duration_seconds=round(end_seconds-start_seconds,3),poster=poster_rel,trace=trace)
                        flow_clips.append(clip)
                except Exception as exc:
                    errors.append(flow_id+": "+type(exc).__name__+": "+str(exc)[:600])
                finally:
                    await context.close()
                raw_source=Path(await video.path())
                raw_target=folder/"raw"/(flow_id+".webm")
                if raw_source.resolve()!=raw_target.resolve():
                    shutil.move(str(raw_source),raw_target)
                for clip in flow_clips:
                    clip.raw_video="raw/"+raw_target.name
                    clip.clip_video="clips/"+clip.scene_id+".webm"
                    try:
                        _split_clip(ffmpeg,raw_target,folder/clip.clip_video,
                                    clip.trace.started_seconds,clip.duration_seconds)
                    except Exception as exc:
                        clip.status="failed"
                        clip.reason=type(exc).__name__+": "+str(exc)[:500]
                        errors.append(clip.scene_id+": "+clip.reason)
                    clips.append(clip)
        finally:
            await browser.close()
    expected={scene.id for scene in storyboard.scenes if scene.scene_type=="demo"}
    recorded={clip.scene_id for clip in clips if clip.status=="recorded" and (folder/clip.clip_video).is_file()}
    status="ready" if recorded==expected and not errors else "failed"
    manifest=RecordingManifest(status=status,source_storyboard=str(storyboard_path),source_plan=str(plan_path),
        source_validation=str(validation_path),site_url=plan.site_url or plan.input_url,viewport=VIEWPORT,
        clips=clips,narrative_scene_ids=[scene.id for scene in storyboard.scenes if scene.scene_type!="demo"],errors=errors)
    (folder/"recording-manifest.json").write_text(manifest.model_dump_json(indent=2),encoding="utf-8")
    lines=["# Recorded demo scenes","",f"Status: {status}",f"Viewport: {VIEWPORT['width']}x{VIEWPORT['height']}",""]
    lines += [f"- {clip.scene_id}: {clip.status}, {clip.duration_seconds:.2f}s, {clip.clip_video or clip.reason}" for clip in clips]
    if errors:
        lines += ["","## Errors",""]+["- "+error for error in errors]
    (folder/"recording.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    return manifest
