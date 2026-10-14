"""Task 3 must stay grounded in a passed Task 2 manifest."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from marketing_video.models import (Checkpoint, CheckpointResult, DemoFlow, DemoPlan, DemoStep,
    DemoValidation, DiscoveryReport, FlowValidation, ProductBrief, ProductClaim, StoryboardDraft,
    StoryboardReview, StoryboardScene, TargetFingerprint)
from marketing_video.storyboard import create_storyboard, load_sources, validate_draft, evidence_bundle


def scene(scene_id, kind, duration, evidence=None, flow="", step=-1):
    return StoryboardScene(id=scene_id,scene_type=kind,duration_seconds=duration,
        headline=scene_id,voiceover="Lời dẫn có căn cứ cho "+scene_id,caption="Nội dung "+scene_id,
        visual_direction="Hiển thị giao diện đã xác minh",evidence_ids=evidence or [],
        flow_id=flow,step_index=step)


def valid_draft():
    return StoryboardDraft(language="vi",tone="rõ ràng",scenes=[
        scene("hook","hook",5,["flow:demo-01"]),
        scene("search","demo",10,["step:demo-01:1"],"demo-01",1),
        scene("details","demo",10,["step:demo-01:2"],"demo-01",2),
        scene("benefit","benefit",8,["claim:0"]),
        scene("cta","cta",7),
    ])


class StoryPlanner:
    model = "fixture-story-writer"
    def __init__(self,drafts=None,reviews=None):
        self.drafts=list(drafts or [valid_draft()])
        self.reviews=list(reviews or [StoryboardReview(approved=True,notes=["Grounded"])])
        self.calls=[]
    async def invoke(self,instruction,data,output_schema,system_prompt=None):
        self.calls.append((output_schema.__name__,data,system_prompt))
        if output_schema is StoryboardDraft:
            return self.drafts.pop(0)
        return self.reviews.pop(0)


class StoryboardTests(unittest.TestCase):
    def sources(self,root,ready=True):
        run=root/'task2'
        (run/'plan').mkdir(parents=True)
        (run/'validation').mkdir()
        (run/'discovery').mkdir()
        target=TargetFingerprint(tag='input',label='Search products',type='search')
        flow=DemoFlow(id='demo-01',source_probe_id='probe-01',source_probe_ids=['probe-01','probe-02'],
            title='Find a product',purpose='Search then inspect details',category='product_functionality',
            initial_url='https://product.test/catalog',steps=[
                DemoStep(operation='navigate',url='https://product.test/catalog'),
                DemoStep(operation='type',target=target,value='apple',source_probe_id='probe-01',
                    checkpoints=[Checkpoint(kind='text_absent',expected='Orange')]),
                DemoStep(operation='click',target=TargetFingerprint(tag='a',label='Apple details',href='https://product.test/apple'),
                    source_probe_id='probe-02',checkpoints=[Checkpoint(kind='url_equals',expected='https://product.test/apple')])],
            checkpoints=[Checkpoint(kind='url_equals',expected='https://product.test/apple')])
        plan=DemoPlan(input_url='https://product.test',site_url='https://product.test/catalog',source_report='source',
            model='fixture',product_name='Fruit Finder',product_type='catalog',audience='Shoppers',
            scope='functional_demo',flows=[flow],limitations=['Checkout was not tested'])
        plan_path=run/'plan/demo-plan.json'
        plan_path.write_text(plan.model_dump_json(indent=2),encoding='utf-8')
        checks=[CheckpointResult(step_index=1,checkpoint=flow.steps[1].checkpoints[0],actual='[text absent]',passed=True),
                CheckpointResult(step_index=2,checkpoint=flow.steps[2].checkpoints[0],actual='https://product.test/apple',passed=True)]
        validation=DemoValidation(source_plan=str(plan_path.resolve()),status='passed',flows=[
            FlowValidation(flow_id='demo-01',status='passed',checkpoints=checks,reason='passed')])
        (run/'validation/validation.json').write_text(validation.model_dump_json(indent=2),encoding='utf-8')
        discovery=DiscoveryReport(input_url='https://product.test',resolved_url='https://product.test/catalog',
            started_at='now',mode='llm',analysis_status='complete',brief=ProductBrief(product_name='Fruit Finder',
                positioning='Find fruit quickly',advertised_features=[ProductClaim(description='Browse a fruit catalog',source_page_ids=['page-01'])],
                limitations=['Purchases were not demonstrated']))
        (run/'discovery/discovery.json').write_text(discovery.model_dump_json(indent=2),encoding='utf-8')
        manifest={'input_url':'https://product.test','status':'ready' if ready else 'needs_research',
            'ready_for_recording':ready,'plan':'plan/demo-plan.json','validation':'validation/validation.json',
            'discovery':'discovery/discovery.json'}
        path=run/'manifest.json'
        path.write_text(json.dumps(manifest),encoding='utf-8')
        return path,plan,validation,discovery

    def test_ready_storyboard_is_grounded_and_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_,_=self.sources(root)
            planner=StoryPlanner()
            result=asyncio.run(create_storyboard(manifest,root/'storyboard',planner))
            self.assertEqual(result.status,'ready')
            self.assertEqual(result.total_duration_seconds,40)
            self.assertEqual([s.step_index for s in result.scenes if s.scene_type=='demo'],[1,2])
            self.assertTrue((root/'storyboard/storyboard.json').exists())
            self.assertTrue((root/'storyboard/evidence.json').exists())
            self.assertEqual([x[0] for x in planner.calls],['StoryboardDraft','StoryboardReview'])
            self.assertTrue(all(x[2] for x in planner.calls))

    def test_manifest_must_be_ready_and_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_,_=self.sources(root,ready=False)
            with self.assertRaisesRegex(ValueError,'ready_for_recording'):
                load_sources(manifest)
            data=json.loads(manifest.read_text())
            data.update(status='ready',ready_for_recording=True,plan='../outside.json')
            manifest.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'inside'):
                load_sources(manifest)

    def test_unknown_evidence_gets_one_revision_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_,_=self.sources(root)
            bad=valid_draft()
            bad.scenes[0].evidence_ids=['invented']
            planner=StoryPlanner(drafts=[bad,valid_draft()])
            result=asyncio.run(create_storyboard(manifest,root/'storyboard',planner))
            self.assertEqual(result.status,'ready')
            draft_calls=[x for x in planner.calls if x[0]=='StoryboardDraft']
            self.assertEqual(len(draft_calls),2)
            self.assertIn('Unknown evidence IDs',draft_calls[1][1]['revision_feedback'])

    def test_rejected_editorial_review_is_not_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            manifest,_,_,_=self.sources(root)
            rejected=StoryboardReview(approved=False,unsupported_scene_ids=['benefit'],notes=['Unsupported outcome'])
            planner=StoryPlanner(drafts=[valid_draft(),valid_draft()],reviews=[rejected,rejected])
            result=asyncio.run(create_storyboard(manifest,root/'storyboard',planner))
            self.assertEqual(result.status,'needs_revision')
            self.assertFalse(result.review.approved)

    def test_demo_cannot_skip_or_reorder_verified_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            _,plan,validation,discovery=self.sources(root)
            evidence=evidence_bundle(plan,validation,discovery)
            draft=valid_draft()
            draft.scenes=[draft.scenes[0],draft.scenes[2],draft.scenes[1],draft.scenes[3],draft.scenes[-1]]
            with self.assertRaisesRegex(ValueError,'once and in order'):
                validate_draft(draft,plan,validation,evidence,40)

    def test_claims_require_a_grounded_benefit_scene(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            _,plan,validation,discovery=self.sources(root)
            evidence=evidence_bundle(plan,validation,discovery)
            draft=valid_draft()
            draft.scenes=[scene for scene in draft.scenes if scene.scene_type!='benefit']
            with self.assertRaisesRegex(ValueError,'duration|benefit'):
                validate_draft(draft,plan,validation,evidence,33)


if __name__=='__main__':
    unittest.main()
