"""Compose storyboard scenes, TTS, captions and a music bed into a final MP4."""
import asyncio
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
import edge_tts
import imageio_ffmpeg
from .models import RecordingManifest, RenderedScene, Storyboard, VideoManifest

SIZE=(1280,720)
FPS=30


def _asset(root,value,label):
    root=Path(root).resolve()
    path=(root/value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(label+" must be an existing file inside the recording run")
    return path


def load_composition_sources(storyboard_path,recording_path):
    storyboard_path=Path(storyboard_path).resolve()
    recording_path=Path(recording_path).resolve()
    storyboard=Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))
    recording=RecordingManifest.model_validate_json(recording_path.read_text(encoding="utf-8"))
    if storyboard.status!="ready" or not storyboard.review.approved:
        raise ValueError("Storyboard is not ready")
    if recording.status!="ready" or Path(recording.source_storyboard).resolve()!=storyboard_path:
        raise ValueError("Recording is not ready or belongs to another storyboard")
    recorded={clip.scene_id:clip for clip in recording.clips if clip.status=="recorded"}
    for scene in storyboard.scenes:
        if scene.scene_type=="demo":
            clip=recorded.get(scene.id)
            if not clip:
                raise ValueError("Missing recorded clip for "+scene.id)
            _asset(recording_path.parent,clip.clip_video,"clip")
            _asset(recording_path.parent,clip.poster,"poster")
    return storyboard_path,recording_path,storyboard,recording,recorded


def _font(size,bold=False):
    names=["arialbd.ttf" if bold else "arial.ttf","segoeuib.ttf" if bold else "segoeui.ttf"]
    roots=[Path("C:/Windows/Fonts"),Path(__file__).resolve().parents[2]/"assets/fonts"]
    for root in roots:
        for name in names:
            path=root/name
            if path.is_file():
                return ImageFont.truetype(str(path),size)
    return ImageFont.load_default()


def _wrap(draw,text,font,max_width):
    words=text.split()
    lines=[]
    current=""
    for word in words:
        candidate=(current+" "+word).strip()
        if not current or draw.textlength(candidate,font=font)<=max_width:
            current=candidate
        else:
            lines.append(current); current=word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _background(poster=None):
    if poster:
        image=Image.open(poster).convert("RGB").resize(SIZE,Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(12))
    else:
        image=Image.new("RGB",SIZE)
        pixels=image.load()
        for y in range(SIZE[1]):
            for x in range(SIZE[0]):
                glow=max(0,1-math.hypot(x-920,y-180)/850)
                pixels[x,y]=(int(7+8*glow),int(10+28*glow),int(18+22*glow))
    image=Image.alpha_composite(image.convert("RGBA"),Image.new("RGBA",SIZE,(2,5,10,165)))
    return image


def render_card(scene,product,index,total,target,poster=None):
    image=_background(poster)
    draw=ImageDraw.Draw(image,"RGBA")
    accent=(84,255,0,255)
    draw.rounded_rectangle((74,62,255,104),18,fill=(20,30,28,225),outline=accent,width=2)
    tag={"hook":"GIỚI THIỆU","benefit":"LỢI ÍCH","cta":"TÌM HIỂU THÊM"}.get(scene.scene_type,scene.scene_type.upper())
    draw.text((94,73),tag,font=_font(18,True),fill=accent)
    draw.text((75,132),product,font=_font(23,True),fill=(225,232,240,255))
    headline=_wrap(draw,scene.headline,_font(56,True),1030)
    box=draw.multiline_textbbox((0,0),headline,font=_font(56,True),spacing=12)
    h=box[3]-box[1]
    draw.multiline_text((75,260-h/2),headline,font=_font(56,True),fill="white",spacing=12)
    caption=_wrap(draw,scene.caption,_font(27),1000)
    draw.multiline_text((78,440),caption,font=_font(27),fill=(210,220,230,255),spacing=8)
    draw.rounded_rectangle((75,650,1205,658),4,fill=(80,90,105,180))
    draw.rounded_rectangle((75,650,75+1130*(index+1)/total,658),4,fill=accent)
    image.convert("RGB").save(target,quality=94)


def render_overlay(scene,product,target):
    image=Image.new("RGBA",SIZE,(0,0,0,0)); draw=ImageDraw.Draw(image,"RGBA")
    draw.rounded_rectangle((34,26,390,70),18,fill=(3,8,15,205),outline=(84,255,0,210),width=2)
    draw.text((54,38),product[:42],font=_font(18,True),fill=(240,245,250,255))
    draw.rounded_rectangle((34,570,1246,690),24,fill=(3,7,14,218))
    draw.rectangle((34,570,44,690),fill=(84,255,0,255))
    draw.text((68,590),scene.headline,font=_font(30,True),fill="white")
    draw.text((68,640),_wrap(draw,scene.caption,_font(21),1100),font=_font(21),fill=(210,220,230,255))
    image.save(target)


def _run(command,label,timeout=180):
    result=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError(label+": "+result.stderr[-900:])


def _probe_duration(ffmpeg,path):
    result=subprocess.run([ffmpeg,"-hide_banner","-i",str(path),"-f","null","-"],capture_output=True,text=True,timeout=120)
    matches=re.findall(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",result.stderr)
    if not matches:
        matches=re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",result.stderr)
    if not matches:
        raise RuntimeError("Could not read media duration: "+str(path))
    hours,minutes,seconds=matches[-1]
    seconds=int(hours)*3600+int(minutes)*60+float(seconds)
    if seconds<=0:
        raise RuntimeError("Media has no duration: "+str(path))
    return seconds


async def _tts(text,voice,target,retries=2):
    for attempt in range(retries+1):
        try:
            await edge_tts.Communicate(text,voice).save(str(target))
            if target.is_file() and target.stat().st_size>1000:
                return
        except Exception:
            if attempt==retries:
                raise
            await asyncio.sleep(2**attempt)
    raise RuntimeError("TTS returned no audio")


def _srt_time(seconds):
    milliseconds=round(seconds*1000)
    hours,milliseconds=divmod(milliseconds,3600000)
    minutes,milliseconds=divmod(milliseconds,60000)
    secs,milliseconds=divmod(milliseconds,1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


async def compose_video(storyboard_path,recording_path,folder,voice=""):
    (storyboard_path,recording_path,storyboard,recording,
     recorded)=load_composition_sources(storyboard_path,recording_path)
    folder=Path(folder).resolve()
    for name in ["cards","overlays","tts","audio","segments"]:
        (folder/name).mkdir(parents=True,exist_ok=True)
    voice=voice or ("vi-VN-HoaiMyNeural" if storyboard.language.lower().startswith("vi") else "en-US-JennyNeural")
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
    scenes=[]; errors=[]; srt=[]; cursor=0.0
    posters=[_asset(recording_path.parent,clip.poster,"poster") for clip in recording.clips if clip.poster]
    for index,scene in enumerate(storyboard.scenes):
        try:
            duration=float(scene.duration_seconds)
            raw_tts=folder/"tts"/(scene.id+".mp3")
            await _tts(scene.voiceover,voice,raw_tts)
            raw_duration=_probe_duration(ffmpeg,raw_tts)
            usable=max(1.0,duration-.35)
            tempo=max(1.0,raw_duration/usable)
            if tempo>2.0:
                raise ValueError(f"Narration for {scene.id} is too long for its scene")
            narration=folder/"audio"/(scene.id+".wav")
            _run([ffmpeg,"-y","-loglevel","error","-i",str(raw_tts),"-af",
                  f"atempo={tempo:.5f},apad,atrim=0:{duration:.3f},aresample=48000",
                  "-ac","2","-c:a","pcm_s16le",str(narration)],"Normalize narration")
            source_clip=""; source_poster=""
            visual=folder/"segments"/(scene.id+".mp4")
            fade_out=max(0,duration-.25)
            fade=f"fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25"
            if scene.scene_type=="demo":
                clip=recorded[scene.id]
                clip_path=_asset(recording_path.parent,clip.clip_video,"clip")
                poster_path=_asset(recording_path.parent,clip.poster,"poster")
                overlay=folder/"overlays"/(scene.id+".png")
                render_overlay(scene,storyboard.product_name,overlay)
                filter_graph=("[0:v]scale=1280:720:force_original_aspect_ratio=decrease,"
                    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black[base];"
                    f"[base][1:v]overlay=0:0,{fade}[v]")
                _run([ffmpeg,"-y","-loglevel","error","-i",str(clip_path),"-loop","1","-i",str(overlay),
                    "-filter_complex",filter_graph,"-map","[v]","-t",f"{duration:.3f}","-r",str(FPS),
                    "-an","-c:v","libx264","-preset","veryfast","-crf","20","-pix_fmt","yuv420p",str(visual)],"Render demo scene")
                source_clip=str(clip_path); source_poster=str(poster_path)
            else:
                poster=posters[0] if scene.scene_type in {"hook","benefit"} and posters else posters[-1] if posters else None
                card=folder/"cards"/(scene.id+".jpg")
                render_card(scene,storyboard.product_name,index,len(storyboard.scenes),card,poster)
                _run([ffmpeg,"-y","-loglevel","error","-loop","1","-i",str(card),"-t",f"{duration:.3f}",
                    "-vf",f"fps={FPS},{fade}","-an","-c:v","libx264","-preset","veryfast","-crf","20",
                    "-pix_fmt","yuv420p",str(visual)],"Render narrative scene")
                source_poster=str(poster) if poster else ""
            scenes.append(RenderedScene(scene_id=scene.id,scene_type=scene.scene_type,duration_seconds=duration,
                video=str(visual.relative_to(folder)),narration=str(narration.relative_to(folder)),
                source_clip=source_clip,source_poster=source_poster))
            srt += [str(index+1),_srt_time(cursor)+" --> "+_srt_time(cursor+duration-.15),scene.voiceover,""]
            cursor+=duration
        except Exception as exc:
            errors.append(scene.id+": "+type(exc).__name__+": "+str(exc)[:700])
            break
    output_video=""; subtitles="subtitles.srt"; narration_mix=""; music=""
    (folder/subtitles).write_text("\n".join(srt),encoding="utf-8-sig")
    if not errors and len(scenes)==len(storyboard.scenes):
        video_list=folder/"video-concat.txt"; audio_list=folder/"audio-concat.txt"
        video_list.write_text("\n".join("file '"+(folder/s.video).resolve().as_posix().replace("'","'\\''")+"'" for s in scenes)+"\n",encoding="utf-8")
        audio_list.write_text("\n".join("file '"+(folder/s.narration).resolve().as_posix().replace("'","'\\''")+"'" for s in scenes)+"\n",encoding="utf-8")
        silent=folder/"video-silent.mp4"; narration=folder/"narration.wav"; bed=folder/"music-bed.wav"
        _run([ffmpeg,"-y","-loglevel","error","-f","concat","-safe","0","-i",str(video_list),"-c","copy",str(silent)],"Concatenate video")
        _run([ffmpeg,"-y","-loglevel","error","-f","concat","-safe","0","-i",str(audio_list),"-c:a","pcm_s16le",str(narration)],"Concatenate narration")
        total=sum(s.duration_seconds for s in scenes)
        _run([ffmpeg,"-y","-loglevel","error","-f","lavfi","-i",f"sine=frequency=110:sample_rate=48000:duration={total:.3f}",
            "-af",f"volume=0.025,lowpass=f=500,afade=t=in:st=0:d=1.2,afade=t=out:st={max(0,total-1.5):.3f}:d=1.5",
            "-ac","2","-c:a","pcm_s16le",str(bed)],"Generate music bed")
        final=folder/"marketing-video.mp4"
        _run([ffmpeg,"-y","-loglevel","error","-i",str(silent),"-i",str(narration),"-i",str(bed),
            "-filter_complex","[1:a]volume=1.15[voice];[2:a]volume=0.8[music];[voice][music]amix=inputs=2:duration=first:normalize=0[a]",
            "-map","0:v:0","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k","-movflags","+faststart",str(final)],"Mux final video")
        if abs(_probe_duration(ffmpeg,final)-total)>.35:
            errors.append("Final video duration does not match the storyboard")
        else:
            output_video=final.name; narration_mix=narration.name; music=bed.name
    status="ready" if output_video and not errors else "failed"
    manifest=VideoManifest(status=status,source_storyboard=str(storyboard_path),source_recording=str(recording_path),
        voice=voice,language=storyboard.language,total_duration_seconds=sum(s.duration_seconds for s in scenes),
        scenes=scenes,output_video=output_video,subtitles=subtitles,narration_mix=narration_mix,music=music,errors=errors)
    (folder/"video-manifest.json").write_text(manifest.model_dump_json(indent=2),encoding="utf-8")
    (folder/"video-report.md").write_text("\n".join(["# Marketing video render","",f"Status: {status}",
        f"Voice: {voice}",f"Duration: {manifest.total_duration_seconds:.2f}s",f"Scenes: {len(scenes)}",
        f"Output: {output_video or 'none'}"]+(["","## Errors",""]+["- "+x for x in errors] if errors else []))+"\n",encoding="utf-8")
    return manifest
