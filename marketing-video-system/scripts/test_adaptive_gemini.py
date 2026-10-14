"""Real Gemini selects workflows for two controlled, different product fixtures."""
import asyncio
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
from test_adaptive_workflows import ProductHandler, ProductPlanner
from marketing_video.discovery import discover
from marketing_video.demo_planner import plan_demo, validate_demo
from marketing_video.llm import Planner
from marketing_video.settings import RUNS, Settings


async def main():
    folder=RUNS/datetime.now(timezone.utc).strftime("adaptive-gemini-fixtures-%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    planner=Planner(Settings.from_env())
    results=[]
    for kind in ['catalog','reports']:
        server=ThreadingHTTPServer(('127.0.0.1',0),ProductHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            target=folder/kind
            url='http://127.0.0.1:'+str(server.server_port)+'/'+kind
            report=await discover(url,target/'discovery',1,2,ProductPlanner(kind))
            plan=await plan_demo(target/'discovery/discovery.json',target/'plan',planner)
            validation=await validate_demo(target/'plan/demo-plan.json',target/'validation')
            results.append({'fixture':kind,'url':url,'product_type_inferred_by_gemini':plan.product_type,
                'flows':[{'title':f.title,'operations':[s.operation for s in f.steps]} for f in plan.flows],
                'validation':validation.status,'plan':str(target/'plan/demo-plan.json')})
            print('Gemini fixture:',kind,validation.status,flush=True)
        finally:
            server.shutdown()
            server.server_close()
    payload={'model':planner.model,'discovery_method':'Controlled browser fixture probes, not Gemini discovery',
        'workflow_selection':'Real configured Gemini','ephemeral_local_servers':True,'results':results}
    (folder/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Report:',folder/'results.json',flush=True)
    return 0 if all(x['validation']=='passed' for x in results) else 1


if __name__=='__main__':
    raise SystemExit(asyncio.run(main()))
