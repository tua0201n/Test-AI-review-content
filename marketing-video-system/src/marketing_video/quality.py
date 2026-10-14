"""Validate the full evidence chain and create a sanitized delivery package."""
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageStat
import imageio_ffmpeg
from .composer import _probe_duration
from .models import (DeliveryFile, DeliveryManifest, RecordingManifest, Storyboard,
                     VideoManifest, QualityCheck)
from .settings import RUNS, ROOT

EXPORTS=ROOT/"artifacts"/"exports"


def _inside(root,value,label):
    root=Path(root).resolve(); path=(root/value).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError(label+" must be an existing file inside its run folder")
    return path


def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seconds(value):
    match=re.fullmatch(r"(\d+):(\d+):(\d+),(\d+)",value.strip())
    if not match:
        raise ValueError("Invalid SRT timestamp: "+value)
    hour,minute,second,millisecond=map(int,match.groups())
    return hour*3600+minute*60+second+millisecond/1000


def parse_srt(text):
    entries=[]
    for block in re.split(r"\r?\n\s*\r?\n",text.lstrip("\ufeff").strip()):
        lines=block.splitlines()
        if len(lines)<3 or " --> " not in lines[1]:
            raise ValueError("Malformed SRT block")
        start,end=lines[1].split(" --> ",1)
        entries.append({"index":int(lines[0]),"start":_seconds(start),"end":_seconds(end),
                        "text":" ".join(line.strip() for line in lines[2:] if line.strip())})
    return entries


def load_quality_sources(video_manifest_path):
    video_manifest_path=Path(video_manifest_path).resolve()
    video=VideoManifest.model_validate_json(video_manifest_path.read_text(encoding="utf-8"))
    if video.status!="ready" or video.errors:
        raise ValueError("Video manifest is not ready")
    storyboard_path=Path(video.source_storyboard).resolve()
    recording_path=Path(video.source_recording).resolve()
    if not storyboard_path.is_file() or not recording_path.is_file():
        raise ValueError("Video source manifests are missing")
    storyboard=Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))
    recording=RecordingManifest.model_validate_json(recording_path.read_text(encoding="utf-8"))
    if storyboard.status!="ready" or not storyboard.review.approved or storyboard.review.unsupported_scene_ids:
        raise ValueError("Storyboard quality gate is not passed")
    if recording.status!="ready" or Path(recording.source_storyboard).resolve()!=storyboard_path:
        raise ValueError("Recording quality gate is not passed")
    final=_inside(video_manifest_path.parent,video.output_video,"final video")
    subtitles=_inside(video_manifest_path.parent,video.subtitles,"subtitles")
    return video_manifest_path,video,storyboard_path,storyboard,recording_path,recording,final,subtitles


def _check(name,condition,details):
    return QualityCheck(name=name,status="passed" if condition else "failed",details=details)


def _media_output(ffmpeg,path):
    result=subprocess.run([ffmpeg,"-hide_banner","-i",str(path),"-af","volumedetect","-f","null","NUL"],
                          capture_output=True,text=True,timeout=180)
    return result.stderr


def _extract_frames(ffmpeg,video,storyboard,folder):
    frames=[]; cursor=0.0
    (folder/"frames").mkdir(parents=True,exist_ok=True)
    for index,scene in enumerate(storyboard.scenes):
        moment=cursor+scene.duration_seconds/2
        path=folder/"frames"/(scene.id+".png")
        result=subprocess.run([ffmpeg,"-y","-loglevel","error","-ss",f"{moment:.3f}","-i",str(video),
            "-frames:v","1",str(path)],capture_output=True,text=True,timeout=90)
        if result.returncode or not path.is_file():
            raise RuntimeError("Could not extract QA frame for "+scene.id+": "+result.stderr[-400:])
        image=Image.open(path).convert("RGB")
        gray=image.convert("L"); stat=ImageStat.Stat(gray)
        frames.append((scene.id,scene.scene_type,path,stat.mean[0],stat.stddev[0]))
        cursor+=scene.duration_seconds
    sheet=Image.new("RGB",(960,540*len(frames)),(13,15,20)); draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf",24) if Path("C:/Windows/Fonts/arialbd.ttf").is_file() else ImageFont.load_default()
    for index,(scene_id,kind,path,mean,stddev) in enumerate(frames):
        image=Image.open(path).convert("RGB").resize((960,540),Image.Resampling.LANCZOS)
        sheet.paste(image,(0,index*540))
        draw.rectangle((0,index*540,340,index*540+42),fill=(0,0,0))
        draw.text((12,index*540+8),f"{scene_id} · {kind}",font=font,fill="white")
    target=folder/"qa-contact-sheet.jpg"; sheet.save(target,quality=88)
    return frames,target


def _slug(value):
    value=re.sub(r"[^a-z0-9]+","-",value.lower()).strip("-")
    return value[:48] or "marketing-video"


def quality_and_package(video_manifest_path,qa_folder=None,export_root=None):
    (video_manifest_path,video,storyboard_path,storyboard,recording_path,
     recording,final,subtitles)=load_quality_sources(video_manifest_path)
    qa_folder=Path(qa_folder or RUNS/datetime.now(timezone.utc).strftime("qa-%Y%m%d-%H%M%S-%f")).resolve()
    qa_folder.mkdir(parents=True,exist_ok=True)
    ffmpeg=imageio_ffmpeg.get_ffmpeg_exe(); checks=[]
    scene_ids=[scene.id for scene in storyboard.scenes]
    checks.append(_check("scene_chain",[scene.scene_id for scene in video.scenes]==scene_ids,
        f"{len(video.scenes)} rendered scenes match {len(scene_ids)} storyboard scenes"))
    demo_ids={scene.id for scene in storyboard.scenes if scene.scene_type=="demo"}
    recorded={clip.scene_id for clip in recording.clips if clip.status=="recorded"}
    checkpoint_results=[check.passed for clip in recording.clips if clip.trace for check in clip.trace.checkpoints]
    checks.append(_check("recording_evidence",demo_ids==recorded and checkpoint_results and all(checkpoint_results),
        f"{len(recorded)} demo scenes and {len(checkpoint_results)} passed checkpoints"))
    expected=sum(scene.duration_seconds for scene in storyboard.scenes); actual=_probe_duration(ffmpeg,final)
    checks.append(_check("duration",abs(actual-expected)<=.35,f"actual {actual:.2f}s; expected {expected:.2f}s"))
    media=_media_output(ffmpeg,final)
    video_ok=bool(re.search(r"Video:\s+h264.*1280x720.*30 fps",media,re.S))
    audio_ok=bool(re.search(r"Audio:\s+aac.*48000 Hz.*stereo",media,re.S))
    checks.append(_check("video_stream",video_ok,"H.264 1280x720 at 30 fps"))
    checks.append(_check("audio_stream",audio_ok,"AAC 48 kHz stereo"))
    mean_match=re.search(r"mean_volume:\s*(-?[\d.]+) dB",media); max_match=re.search(r"max_volume:\s*(-?[\d.]+) dB",media)
    mean=float(mean_match.group(1)) if mean_match else -99; peak=float(max_match.group(1)) if max_match else 99
    checks.append(_check("audio_level",-45<=mean<=-8 and -30<=peak<=0,f"mean {mean:.1f} dB; peak {peak:.1f} dB"))
    entries=parse_srt(subtitles.read_text(encoding="utf-8-sig"))
    subtitle_text=[re.sub(r"\s+"," ",entry["text"]).strip() for entry in entries]
    expected_text=[re.sub(r"\s+"," ",scene.voiceover).strip() for scene in storyboard.scenes]
    monotonic=all(entry["start"]<entry["end"] and (i==0 or entry["start"]>=entries[i-1]["end"])
                  for i,entry in enumerate(entries))
    checks.append(_check("subtitles",subtitle_text==expected_text and monotonic,
        f"{len(entries)} ordered subtitle blocks match the voiceover"))
    frames,contact=_extract_frames(ffmpeg,final,storyboard,qa_folder)
    visible=all(mean>5 and stddev>5 for _,_,_,mean,stddev in frames)
    checks.append(_check("visual_samples",visible,
        "; ".join(f"{scene}: brightness {mean:.1f}, contrast {stddev:.1f}" for scene,_,_,mean,stddev in frames)))
    errors=[check.name+": "+check.details for check in checks if check.status=="failed"]
    qa_payload={"status":"passed" if not errors else "failed","product_name":storyboard.product_name,
        "video":str(final),"checks":[check.model_dump() for check in checks],"errors":errors}
    (qa_folder/"qa-report.json").write_text(json.dumps(qa_payload,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# Final video QA","",f"Status: {qa_payload['status']}",f"Product: {storyboard.product_name}",""]
    lines += [f"- {check.status.upper()} · {check.name}: {check.details}" for check in checks]
    (qa_folder/"qa-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    delivery=DeliveryManifest(status="failed" if errors else "ready",product_name=storyboard.product_name,
        website=recording.site_url,duration_seconds=actual,resolution=video.resolution,checks=checks,errors=errors)
    if errors:
        (qa_folder/"delivery-manifest.json").write_text(delivery.model_dump_json(indent=2),encoding="utf-8")
        return qa_folder,delivery
    export_root=Path(export_root or EXPORTS).resolve(); export_root.mkdir(parents=True,exist_ok=True)
    package=export_root/(_slug(storyboard.product_name)+"-"+datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    package.mkdir()
    shutil.copy2(final,package/"marketing-video.mp4")
    shutil.copy2(subtitles,package/"subtitles.srt")
    shutil.copy2(contact,package/"qa-contact-sheet.jpg")
    shutil.copy2(qa_folder/"qa-report.md",package/"qa-report.md")
    provenance={"product_name":storyboard.product_name,"website":recording.site_url,"language":storyboard.language,
        "voice":video.voice,"duration_seconds":actual,"scene_ids":scene_ids,
        "demo_scene_ids":sorted(demo_ids),"checkpoint_count":len(checkpoint_results),"editorial_review":"approved"}
    (package/"provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding="utf-8")
    (package/"README.txt").write_text(
        "Gói video marketing hoàn chỉnh\n\nmarketing-video.mp4: video phát hành\nsubtitles.srt: phụ đề đầy đủ\n"
        "qa-report.md: kết quả kiểm tra kỹ thuật\nqa-contact-sheet.jpg: khung hình đại diện\n"
        "provenance.json: nguồn gốc và phạm vi kiểm chứng\nchecksums.sha256: mã kiểm tra toàn vẹn\n",
        encoding="utf-8-sig")
    payload=[]
    for path in sorted(p for p in package.iterdir() if p.is_file()):
        payload.append(DeliveryFile(path=path.name,bytes=path.stat().st_size,sha256=_sha(path)))
    delivery.files=payload; delivery.archive=package.name+".zip"
    manifest_path=package/"delivery-manifest.json"
    manifest_path.write_text(delivery.model_dump_json(indent=2),encoding="utf-8")
    checksums=payload+[DeliveryFile(path=manifest_path.name,bytes=manifest_path.stat().st_size,sha256=_sha(manifest_path))]
    (package/"checksums.sha256").write_text("\n".join(item.sha256+"  "+item.path for item in checksums)+"\n",encoding="ascii")
    archive=package.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(package.iterdir()):
            if path.is_file():
                bundle.write(path,arcname=path.name)
    shutil.copy2(package/"delivery-manifest.json",qa_folder/"delivery-manifest.json")
    (qa_folder/"archive.sha256").write_text(_sha(archive)+"  "+archive.name+"\n",encoding="ascii")
    return qa_folder,delivery
