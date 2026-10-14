"""Task 4 records only approved, replayed storyboard actions."""
import asyncio
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from marketing_video.models import (Checkpoint, CheckpointResult, DemoFlow, DemoPlan, DemoStep,
    DemoValidation, FlowValidation, Storyboard, StoryboardReview, StoryboardScene, TargetFingerprint)
from marketing_video.recording import load_recording_sources, record_storyboard


class RecordingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pages={
            '/catalog':"""<title>Catalog</title><h1>Fruit catalog</h1>
              <input type=search placeholder='Search products' oninput="document.getElementById('orange').hidden=this.value==='apple'">
              <div>Apple <a href='/apple'>View Apple details</a></div><div id=orange>Orange</div>""",
            '/apple':"<title>Apple</title><h1>Apple product details</h1><p>Origin: local orchard</p>"}
        self.send_response(200)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(pages.get(self.path,'<h1>Missing</h1>').encode())
    def log_message(self,*args):
        pass


class RecordingTests(unittest.TestCase):
    def server(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),RecordingHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def sources(self,root,url,approved=True):
        search=TargetFingerprint(tag='input',label='Search products',type='search')
        detail=TargetFingerprint(tag='a',label='View Apple details',href=url.replace('/catalog','/apple'))
        steps=[DemoStep(operation='navigate',url=url),
            DemoStep(operation='type',target=search,value='apple',source_probe_id='p1',
                checkpoints=[Checkpoint(kind='url_equals',expected=url),Checkpoint(kind='text_absent',expected='Orange')]),
            DemoStep(operation='click',target=detail,source_probe_id='p2',
                checkpoints=[Checkpoint(kind='url_equals',expected=url.replace('/catalog','/apple')),
                             Checkpoint(kind='text_contains',expected='Apple product details')])]
        flow=DemoFlow(id='demo-01',source_probe_id='p1',source_probe_ids=['p1','p2'],title='Find fruit',
            purpose='Search and inspect a product',category='product_functionality',initial_url=url,
            steps=steps,checkpoints=steps[-1].checkpoints)
        plan=DemoPlan(input_url=url,site_url=url,source_report='fixture',model='fixture',product_name='Fruit',
            product_type='catalog',audience='Shoppers',scope='functional_demo',flows=[flow])
        plan_path=root/'plan.json'; plan_path.write_text(plan.model_dump_json(indent=2),encoding='utf-8')
        validation=DemoValidation(source_plan=str(plan_path.resolve()),status='passed',flows=[FlowValidation(
            flow_id='demo-01',status='passed',reason='passed',checkpoints=[
                CheckpointResult(step_index=1,checkpoint=steps[1].checkpoints[0],actual=url,passed=True),
                CheckpointResult(step_index=2,checkpoint=steps[2].checkpoints[0],actual=url.replace('/catalog','/apple'),passed=True)])])
        validation_path=root/'validation.json'; validation_path.write_text(validation.model_dump_json(indent=2),encoding='utf-8')
        def scene(scene_id,kind,duration,evidence=None,step=-1):
            return StoryboardScene(id=scene_id,scene_type=kind,duration_seconds=duration,headline=scene_id,
                voiceover=scene_id,caption=scene_id,visual_direction=scene_id,evidence_ids=evidence or [],
                flow_id='demo-01' if kind=='demo' else '',step_index=step)
        review=StoryboardReview(approved=approved,unsupported_scene_ids=[] if approved else ['search'])
        board=Storyboard(status='ready' if approved else 'needs_revision',source_manifest=str(root/'manifest.json'),
            source_plan=str(plan_path),source_validation=str(validation_path),source_discovery=str(root/'discovery.json'),
            model='fixture',product_name='Fruit',product_type='catalog',audience='Shoppers',language='en',tone='clear',
            total_duration_seconds=10,scenes=[scene('hook','hook',2,['product']),
                scene('search','demo',2,['step:demo-01:1'],1),scene('details','demo',2,['step:demo-01:2'],2),
                scene('cta','cta',2)],review=review)
        board_path=root/'storyboard.json'; board_path.write_text(board.model_dump_json(indent=2),encoding='utf-8')
        return board_path

    def test_unapproved_storyboard_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=self.sources(root,'http://127.0.0.1:1/catalog',approved=False)
            with self.assertRaisesRegex(ValueError,'not approved'):
                load_recording_sources(path)

    def test_records_clips_cursor_trace_and_checkpoints(self):
        server=self.server()
        url=f'http://127.0.0.1:{server.server_port}/catalog'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=self.sources(root,url)
            result=asyncio.run(record_storyboard(path,root/'recording'))
            self.assertEqual(result.status,'ready',result.errors)
            self.assertEqual([clip.scene_id for clip in result.clips],['search','details'])
            self.assertEqual(result.narrative_scene_ids,['hook','cta'])
            for clip in result.clips:
                self.assertTrue((root/'recording'/clip.raw_video).is_file())
                self.assertGreater((root/'recording'/clip.clip_video).stat().st_size,1000)
                self.assertTrue((root/'recording'/clip.poster).is_file())
                self.assertTrue(all(check.passed for check in clip.trace.checkpoints))
                self.assertNotEqual(clip.trace.cursor_from,clip.trace.cursor_to)
            self.assertTrue((root/'recording/recording-manifest.json').is_file())


if __name__=='__main__':
    unittest.main()
