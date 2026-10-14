"""Different product URLs must produce different continuous, verified workflows."""
import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from marketing_video.models import (ExplorationPlan, ProbeRequest, ProductBrief, WorkflowSelection, WorkflowChoice,
                                    DemoPlan, DiscoveryReport)
from marketing_video.pipeline import prepare_demo
from marketing_video.demo_planner import compile_plan, validate_demo, eligible_probes

CATALOG = """<title>Fruit catalog</title><h1>Fruit catalog</h1>
<input type=search placeholder='Search products' oninput="document.getElementById('orange').hidden=this.value.toLowerCase()==='apple'">
<div id=apple>Apple: fresh red fruit <a href='/items/apple'>View Apple details</a></div>
<div id=orange>Orange: citrus fruit</div>
"""
DOCS = """<title>Developer documentation</title><h1>Developer documentation</h1>
<details><summary>Connection troubleshooting</summary><p>Set the service endpoint before connecting.</p></details>
<a href='/guide'>Read integration guide</a>"""
REPORTS = """<title>Analytics dashboard</title><h1>Analytics dashboard</h1>
<select aria-label='Filter period' onchange="document.getElementById('results').textContent=this.value==='week'?'Week: 3 signups':'Month: 25 signups'">
<option value=month>Month</option><option value=week>Week</option></select>
<p id=results>Month: 25 signups</p>
<button type=button aria-expanded=false onclick="this.setAttribute('aria-expanded','true');document.getElementById('breakdown').hidden=false">Show breakdown</button>
<p id=breakdown hidden>Breakdown: organic and referral traffic</p>"""


class ProductHandler(BaseHTTPRequestHandler):
    writes = 0
    detail_requests = 0
    def do_GET(self):
        if self.path=='/redirect':
            self.send_response(302)
            self.send_header('Location','http://127.0.0.1:'+str(self.server.server_port)+'/catalog')
            self.end_headers()
            return
        routes = {'/catalog':CATALOG,'/docs':DOCS,'/reports':REPORTS,
            '/items/apple':'<h1>Apple product details</h1><p>Origin: local orchard</p><form method=post><button>Buy now</button></form>',
            '/guide':'<h1>Integration guide</h1><p>Connect using the documented endpoint.</p>'}
        if self.path in {'/guide','/items/apple'}:
            type(self).detail_requests += 1
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(routes.get(self.path,'<h1>Unknown page</h1>').encode())
    def do_POST(self):
        type(self).writes += 1
        self.send_response(200)
        self.end_headers()
    def log_message(self,*args):
        pass


class ProductPlanner:
    model = 'fixture-adaptive-planner'
    def __init__(self,kind):
        self.kind=kind
        self.calls=[]
    async def plan(self,page):
        specs={'catalog':[('Search products','type','apple'),('View Apple details','click','')],
               'docs':[('Connection troubleshooting','click',''),('Read integration guide','click','')],
               'reports':[('Filter period','select','week'),('Show breakdown','click','')]}
        probes=[]
        for label,operation,value in specs[self.kind]:
            c=next(c for c in page.controls if c.label==label)
            probes.append(ProbeRequest(control_id=c.id,operation=operation,value=value,feature=label,expected_observation='Actual result changes'))
        return ExplorationPlan(page_purpose=page.title,probes=probes)
    async def brief(self,report):
        return ProductBrief(product_name=report.pages[0].title,positioning='Fixture '+self.kind,
            recommended_demo_probe_ids=[p.id for p in report.probes if p.status=='demonstrated'])
    async def invoke(self,instruction,data,schema):
        self.calls.append(data)
        return WorkflowSelection(product_name=data['brief']['product_name'],product_type=self.kind,audience='Demo users',
            choices=[WorkflowChoice(probe_ids=[p['id'] for p in data['eligible_probes']],title='Task for '+self.kind,
                                   purpose='Demonstrate the observed result',category='product_functionality')])


class AdaptiveWorkflowTests(unittest.TestCase):
    def server(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),ProductHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_three_product_types_from_url_to_verified_multistep_demo(self):
        with tempfile.TemporaryDirectory() as directory:
            sequences=[]
            for kind in ['catalog','docs','reports']:
                server=self.server()
                url='http://127.0.0.1:'+str(server.server_port)+'/'+kind
                planner=ProductPlanner(kind)
                folder,manifest=asyncio.run(prepare_demo(url,planner,max_pages=1,max_probes=2,folder=Path(directory)/kind))
                self.assertTrue(manifest['ready_for_recording'],manifest)
                self.assertEqual(manifest['status'],'ready')
                self.assertEqual(manifest['product_type'],kind)
                plan=DemoPlan.model_validate_json((folder/'plan/demo-plan.json').read_text())
                flow=plan.flows[0]
                self.assertEqual(len(flow.source_probe_ids),2)
                self.assertEqual(len(flow.steps),3)
                self.assertTrue(all(step.checkpoints for step in flow.steps[1:]))
                sequences.append([step.operation for step in flow.steps])
                self.assertEqual(planner.calls[0]['input_url'],url)
                self.assertTrue(planner.calls[0]['continuity_edges'])
                self.assertNotIn('aisoeasy',str(planner.calls).lower())
                report=DiscoveryReport.model_validate_json((folder/'discovery/discovery.json').read_text())
                bad=WorkflowSelection(product_name='Bad',product_type=kind,audience='Test',choices=[
                    WorkflowChoice(probe_ids=['invented'],title='Bad',purpose='Bad',category='product_functionality')])
                with self.assertRaises(ValueError):
                    compile_plan(bad,report,folder/'discovery/discovery.json')
                if kind=='catalog':
                    self.assertTrue(any(c.kind=='text_absent' for c in flow.steps[1].checkpoints))
                    report.probes[0].after.text='No products found'
                    self.assertNotIn(report.probes[0].id,[p.id for p in eligible_probes(report)])
            self.assertEqual(sequences,[['navigate','type','click'],['navigate','click','click'],['navigate','select','click']])
            self.assertEqual(ProductHandler.writes,0)

    def test_failure_at_intermediate_step_stops_remaining_actions(self):
        server=self.server()
        with tempfile.TemporaryDirectory() as directory:
            folder,manifest=asyncio.run(prepare_demo('http://127.0.0.1:'+str(server.server_port)+'/docs',ProductPlanner('docs'),
                max_pages=1,max_probes=2,folder=Path(directory)/'run'))
            path=folder/'plan/demo-plan.json'
            plan=DemoPlan.model_validate_json(path.read_text())
            plan.flows[0].steps[1].checkpoints[0].expected='Impossible result'
            path.write_text(plan.model_dump_json(),encoding='utf-8')
            before=ProductHandler.detail_requests
            result=asyncio.run(validate_demo(path,Path(directory)/'failed'))
            self.assertEqual(result.status,'failed')
            self.assertEqual(ProductHandler.detail_requests,before)

    def test_disconnected_probes_cannot_be_joined(self):
        server=self.server()
        with tempfile.TemporaryDirectory() as directory:
            folder,_=asyncio.run(prepare_demo('http://127.0.0.1:'+str(server.server_port)+'/catalog',ProductPlanner('catalog'),
                max_pages=1,max_probes=2,folder=Path(directory)/'run'))
            report=DiscoveryReport.model_validate_json((folder/'discovery/discovery.json').read_text())
            report.probes[1].before.url='http://127.0.0.1:'+str(server.server_port)+'/another-state'
            selection=WorkflowSelection(product_name='Bad chain',product_type='catalog',audience='Users',choices=[
                WorkflowChoice(probe_ids=[p.id for p in report.probes],title='Bad chain',purpose='Test',category='product_functionality')])
            with self.assertRaisesRegex(ValueError,'continuous workflow'):
                compile_plan(selection,report,folder/'discovery/discovery.json')


    def test_invalid_llm_ids_are_repaired_with_compiler_feedback(self):
        class RepairingPlanner(ProductPlanner):
            attempts=0
            async def invoke(self,instruction,data,schema):
                self.attempts+=1
                if self.attempts==1:
                    return WorkflowSelection(product_name='Catalog',product_type='catalog',audience='Users',choices=[
                        WorkflowChoice(probe_ids=['unknown'],title='Bad proposal',purpose='Test',category='product_functionality')])
                self.assert_feedback=data.get('compiler_feedback','')
                return await super().invoke(instruction,data,schema)
        server=self.server()
        planner=RepairingPlanner('catalog')
        with tempfile.TemporaryDirectory() as directory:
            _,manifest=asyncio.run(prepare_demo('http://127.0.0.1:'+str(server.server_port)+'/catalog',planner,
                max_pages=1,max_probes=2,folder=Path(directory)/'run'))
            self.assertTrue(manifest['ready_for_recording'])
            self.assertEqual(planner.attempts,2)
            self.assertIn('unknown',planner.assert_feedback)

    def test_incomplete_discovery_does_not_advance_to_recording(self):
        from unittest.mock import AsyncMock,patch
        report=DiscoveryReport(input_url='https://fixture.test/',started_at='now',mode='llm',status='partial',analysis_status='unavailable')
        with tempfile.TemporaryDirectory() as directory:
            planner=ProductPlanner('catalog')
            with patch('marketing_video.pipeline.discover',new_callable=AsyncMock,return_value=report):
                folder,manifest=asyncio.run(prepare_demo(report.input_url,planner,folder=Path(directory)/'run'))
            self.assertFalse(manifest['ready_for_recording'])
            self.assertEqual(manifest['status'],'incomplete_discovery')
            self.assertEqual(planner.calls,[])
            self.assertTrue((folder/'manifest.json').exists())


    def test_entry_redirect_is_canonicalized(self):
        server=self.server()
        with tempfile.TemporaryDirectory() as directory:
            requested='http://localhost:'+str(server.server_port)+'/redirect'
            folder,manifest=asyncio.run(prepare_demo(requested,ProductPlanner('catalog'),max_pages=1,max_probes=2,
                folder=Path(directory)/'run'))
            self.assertTrue(manifest['ready_for_recording'],manifest)
            self.assertEqual(manifest['input_url'],requested)
            self.assertEqual(manifest['resolved_url'],'http://127.0.0.1:'+str(server.server_port)+'/catalog')
            plan=DemoPlan.model_validate_json((folder/'plan/demo-plan.json').read_text())
            self.assertEqual(plan.site_url,manifest['resolved_url'])
