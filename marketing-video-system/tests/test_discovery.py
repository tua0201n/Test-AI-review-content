"""Check that real UI outcomes, not typing or marketing copy, establish demo evidence."""
import asyncio
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from marketing_video.discovery import discover, permitted, validate_brief, assess_changes, recheck_discovery
from marketing_video.models import PageEvidence, Control, ExplorationPlan, ProbeRequest, ProductBrief, DiscoveryReport

HOME = """<html><head><title>Fixture Product</title></head><body>
<h1>Fixture Product</h1><p>Advertised: automatic certificates</p>
<a href='/tools'>Tools</a>
<input type='search' placeholder='Search items' oninput="document.getElementById('results').textContent=this.value==='apple'?'1 matching item: Apple':'No matches'">
<div id='results'>3 items</div>
<input type='search' placeholder='Search inert'>
</body></html>"""
TOOLS = """<html><head><title>Tools</title></head><body>
<button type='button' aria-expanded='false' onclick="this.setAttribute('aria-expanded',this.getAttribute('aria-expanded')==='false'?'true':'false');document.getElementById('details').hidden=!document.getElementById('details').hidden">More details</button>
<div id='details' hidden>Functional details revealed</div>
<form method='post'><button>Buy now</button></form><a href='/child'>Child details</a>
</body></html>"""


class FixtureHandler(BaseHTTPRequestHandler):
    writes = 0

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write((TOOLS if self.path == '/tools' else HOME).encode())

    def do_POST(self):
        type(self).writes += 1
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class FixturePlanner:
    model = 'fixture-planner'

    async def plan(self, page):
        probes = []
        for c in page.controls:
            if c.tag == 'input':
                probes.append(ProbeRequest(control_id=c.id, operation='type', value='apple', feature=c.label, expected_observation='Result list changes'))
            elif c.tag == 'button':
                probes.append(ProbeRequest(control_id=c.id, operation='click', feature=c.label, expected_observation='Details revealed'))
        return ExplorationPlan(page_purpose=page.title, probes=probes[:2], priority_urls=[c.href for c in page.controls if c.href])

    async def brief(self, report):
        return ProductBrief(product_name='Fixture Product', positioning='Fixture',
            recommended_demo_probe_ids=[p.id for p in report.probes if p.status == 'demonstrated'])


class DiscoveryTests(unittest.TestCase):
    def test_query_present_in_unchanged_body_is_not_a_result_change(self):
        page = PageEvidence(id='page-1',url='https://example.test/',title='Tools',
            text='Website tools\n3 results',screenshot='test.png',controls=[])
        changes = assess_changes(page,page,{'value':''},{'value':'Website'})
        self.assertEqual(changes,[])

    def test_loading_screen_is_not_functional_evidence(self):
        before = PageEvidence(id='before',url='https://example.test/learn',title='Learn',text='Courses',screenshot='before.png',controls=[])
        after = before.model_copy(update={'url':'https://example.test/path','text':'Loading...\nHome'})
        self.assertEqual(assess_changes(before,after,{},{}),[])

    def test_semantics_not_website_labels_determine_read_only_buttons(self):
        req = ProbeRequest(control_id='x',operation='click',feature='section',expected_observation='content')
        for label in ['Practical tasks','Peer review','Friends','Region','Learning path']:
            self.assertIsNotNone(permitted(Control(id='x',tag='button',label=label),req,'https://example.test/'))
            self.assertIsNone(permitted(Control(id='x',tag='button',label=label,role='tab'),req,'https://example.test/'))
        self.assertIsNone(permitted(Control(id='x',tag='button',label='Last month',interaction_hint='filter'),req,'https://example.test/'))
        self.assertIsNotNone(permitted(Control(id='x',tag='button',label='Register',role='tab'),req,'https://example.test/'))

    def test_course_detail_link_does_not_enroll(self):
        req = ProbeRequest(control_id='x',operation='click',feature='details',expected_observation='content')
        self.assertIsNone(permitted(Control(id='x',tag='a',label='View details & register',href='https://example.test/app/course/abc-123'),req,'https://example.test/'))
        for href in ['https://example.test/app/course/abc/enroll','https://example.test/app/course/delete','https://outside.test/app/course/abc']:
            self.assertIsNotNone(permitted(Control(id='x',tag='a',label='Register',href=href),req,'https://example.test/'))

    def test_read_only_policy(self):
        root = 'https://example.test/'
        cases = [
            Control(id='x', tag='button', label='Search', form_submit=True),
            Control(id='x', tag='a', label='Details', href=root+'delete'),
            Control(id='x', tag='a', label='Details', href='https://outside.test/'),
        ]
        req = ProbeRequest(control_id='x', operation='click', feature='x', expected_observation='x')
        for c in cases:
            self.assertIsNotNone(permitted(c, req, root))

    def test_unproven_demo_is_rejected(self):
        report = DiscoveryReport(input_url='https://example.test', started_at='now', mode='offline')
        brief = ProductBrief(product_name='Test', positioning='Test', recommended_demo_probe_ids=['invented'])
        with self.assertRaises(ValueError):
            validate_brief(brief, report)

    def test_llm_failure_preserves_browser_evidence(self):
        class UnavailablePlanner:
            model = 'unavailable-model'
            calls = 0

            async def plan(self, page):
                self.calls += 1
                raise RuntimeError('LLM gateway unavailable')

        server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        planner = UnavailablePlanner()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = asyncio.run(discover('http://127.0.0.1:'+str(server.server_port)+'/',
                    Path(directory)/'run', max_pages=2, max_probes=4, planner=planner))
                self.assertEqual(planner.calls, 1)
                self.assertEqual(report.analysis_status, 'unavailable')
                self.assertEqual(report.status, 'partial')
                self.assertEqual(len(report.pages), 2)
                self.assertTrue(report.probes)
                self.assertIsNone(report.brief)
        finally:
            server.shutdown()
            server.server_close()

    def test_reached_page_is_inspected_before_its_child_links(self):
        class NavigationPlanner:
            model = 'navigation-planner'

            async def plan(self, page):
                link = next((c for c in page.controls if c.label == 'Tools'), None)
                probes = [] if link is None else [ProbeRequest(control_id=link.id, operation='click',
                    feature='Open tools', expected_observation='Tools page opens')]
                return ExplorationPlan(page_purpose=page.title, probes=probes, priority_urls=[])

            async def brief(self, report):
                return ProductBrief(product_name='Fixture Product', positioning='Fixture')

        server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                report = asyncio.run(discover('http://127.0.0.1:'+str(server.server_port)+'/',
                    Path(directory)/'run', max_pages=2, max_probes=1, planner=NavigationPlanner()))
                self.assertEqual(len(report.pages), 2)
                self.assertTrue(report.pages[1].url.endswith('/tools'))
        finally:
            server.shutdown()
            server.server_close()

    def test_functional_search_disclosure_and_inert_input(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)/'run'
                report = asyncio.run(discover('http://127.0.0.1:'+str(server.server_port)+'/', folder,
                    max_pages=2, max_probes=4, planner=FixturePlanner()))
                self.assertEqual(report.status, 'complete')
                outcomes = {p.request.feature:p for p in report.probes}
                self.assertEqual(outcomes['Search items'].status, 'demonstrated')
                self.assertIn('1 matching item: Apple', outcomes['Search items'].after.text)
                self.assertEqual(outcomes['Search inert'].status, 'no_observable_result')
                self.assertEqual(outcomes['More details'].status, 'demonstrated')
                self.assertEqual(outcomes['Buy now'].status, 'blocked_action')
                self.assertEqual(FixtureHandler.writes, 0)
                self.assertTrue((folder/'discovery.json').exists())
                rechecked = asyncio.run(recheck_discovery(folder/'discovery.json',Path(directory)/'rechecked',FixturePlanner()))
                self.assertEqual(rechecked.analysis_status,'complete')
                self.assertEqual([p.status for p in rechecked.probes],[p.status for p in report.probes])
                self.assertTrue((Path(directory)/'rechecked'/'source.json').exists())
                for p in report.probes:
                    self.assertTrue((folder/p.before.screenshot).exists())
                    if p.after:
                        self.assertTrue((folder/p.after.screenshot).exists())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
