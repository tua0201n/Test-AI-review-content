"""Check that real UI outcomes, not typing or marketing copy, establish demo evidence."""
import asyncio
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from marketing_video.discovery import discover, permitted, validate_brief
from marketing_video.models import Control, ExplorationPlan, ProbeRequest, ProductBrief, DiscoveryReport

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
<form method='post'><button>Buy now</button></form>
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
                for p in report.probes:
                    self.assertTrue((folder/p.before.screenshot).exists())
                    if p.after:
                        self.assertTrue((folder/p.after.screenshot).exists())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
