"""Evidence selection and checkpoint replay tests for Task 2."""
import asyncio
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from test_discovery import FixtureHandler, FixturePlanner
from marketing_video.discovery import discover
from marketing_video.demo_planner import compile_plan, validate_demo
from marketing_video.models import DemoSelection, DemoChoice


class DemoPlannerTests(unittest.TestCase):
    def test_grounded_plan_and_replay(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report = asyncio.run(discover('http://127.0.0.1:'+str(server.server_port)+'/',root/'discovery',
                    max_pages=2,max_probes=4,planner=FixturePlanner()))
                choices = [DemoChoice(probe_id=p.id,title=p.request.feature,purpose='Demonstrate actual result',
                    category='product_functionality') for p in report.probes if p.status=='demonstrated']
                selection = DemoSelection(product_name='Fixture Product',audience='Testers',choices=choices)
                plan = compile_plan(selection,report,root/'discovery'/'discovery.json')
                self.assertEqual(plan.scope,'functional_demo')
                self.assertEqual(len(plan.flows),2)
                self.assertTrue(all(f.checkpoints for f in plan.flows))
                path = root/'demo-plan.json'
                path.write_text(plan.model_dump_json(indent=2),encoding='utf-8')
                validation = asyncio.run(validate_demo(path,root/'validation'))
                self.assertEqual(validation.status,'passed')
                self.assertTrue(all(c.passed for f in validation.flows for c in f.checkpoints))
                for flow, result in zip(plan.flows, validation.flows):
                    self.assertEqual(len(result.checkpoints),
                        sum(len(step.checkpoints) for step in flow.steps))
                # An impossible expectation must not be reported as a successful demo.
                plan.flows = plan.flows[:1]
                plan.flows[0].checkpoints[0].expected = 'A result that never exists'
                path.write_text(plan.model_dump_json(indent=2),encoding='utf-8')
                failed = asyncio.run(validate_demo(path,root/'validation-failed'))
                self.assertEqual(failed.status,'failed')
                # A typed field without updated results is not eligible.
                inert = next(p for p in report.probes if p.request.feature=='Search inert')
                bad = DemoSelection(product_name='Fixture',audience='Testers',choices=[
                    DemoChoice(probe_id=inert.id,title='Search',purpose='Unproven',category='product_functionality')])
                with self.assertRaisesRegex(ValueError,'no demonstrated evidence'):
                    compile_plan(bad,report,root/'discovery'/'discovery.json')
                self.assertEqual(FixtureHandler.writes,0)
        finally:
            server.shutdown()
            server.server_close()


if __name__=='__main__':
    unittest.main()
