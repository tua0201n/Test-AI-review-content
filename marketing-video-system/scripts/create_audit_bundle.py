"""Combine completed AI discovery reports while preserving their evidence provenance."""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from marketing_video.models import DiscoveryReport, ProductBrief
from marketing_video.discovery import save_report, validate_brief
from marketing_video.settings import RUNS

sources = [Path(p).resolve() for p in sys.argv[1:]]
if not sources:
    raise SystemExit('Provide completed discovery.json sources')
reports = [DiscoveryReport.model_validate_json(p.read_text(encoding='utf-8')) for p in sources]
if any(r.status != 'complete' or r.analysis_status != 'complete' or not r.brief for r in reports):
    raise SystemExit('Every source must have completed AI analysis')
folder = RUNS / datetime.now(timezone.utc).strftime('functional-audit-%Y%m%d-%H%M%S-%f')
(folder/'screenshots').mkdir(parents=True)
report = DiscoveryReport(input_url=reports[0].input_url,started_at=datetime.now(timezone.utc).isoformat(),
    mode='llm',model=reports[0].model,analysis_status='complete')
claims, recommended, limitations = [], [], []
manifest = []
for i,(source,r) in enumerate(zip(sources,reports),1):
    prefix = f'e{i}-'
    def snapshot_copy(page):
        result = page.model_copy(deep=True)
        result.id = prefix + page.id
        result.screenshot = 'screenshots/' + prefix + Path(page.screenshot).name
        shutil.copy2(source.parent/page.screenshot,folder/result.screenshot)
        return result
    report.pages.extend(snapshot_copy(p) for p in r.pages)
    for p in r.probes:
        result = p.model_copy(deep=True)
        result.id = prefix + p.id
        result.page_id = prefix + p.page_id
        result.before = snapshot_copy(p.before)
        result.after = snapshot_copy(p.after) if p.after else None
        report.probes.append(result)
    for claim in r.brief.advertised_features:
        claims.append(claim.model_copy(update={'source_page_ids':[prefix+x for x in claim.source_page_ids]}))
    recommended.extend(prefix+x for x in r.brief.recommended_demo_probe_ids)
    limitations.extend(r.brief.limitations)
    manifest.append({'prefix':prefix,'source':str(source),'method':'Evidence and AI brief copied from completed source; identifiers namespaced'})
limitations += ['Khảo sát có giới hạn trang/thao tác; không phải kiểm thử toàn bộ sản phẩm.',
    'Mở tab và thấy danh sách trống chỉ chứng minh giao diện chuyển mục; không chứng minh hoàn thành nhiệm vụ.',
    'Khóa học mẫu chưa được đăng ký: chưa kiểm chứng phát video, hoàn thành bài học, chứng chỉ hoặc cộng XP.']
report.brief = ProductBrief(product_name=reports[0].brief.product_name,positioning=reports[0].brief.positioning,
    audience_hypotheses=list(dict.fromkeys(x for r in reports for x in r.brief.audience_hypotheses)),
    advertised_features=claims,recommended_demo_probe_ids=list(dict.fromkeys(recommended)),
    limitations=list(dict.fromkeys(limitations)))
validate_brief(report.brief,report)
save_report(report,folder)
(folder/'sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Bundle:',folder,flush=True)
print('Pages:',len(report.pages),'Probes:',len(report.probes),flush=True)
