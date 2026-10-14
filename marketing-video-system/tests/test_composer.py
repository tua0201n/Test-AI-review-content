"""Task 5 composes a traceable MP4 without requiring live TTS in tests."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import imageio_ffmpeg
from marketing_video.models import (RecordedClip, RecordingManifest, Storyboard, StoryboardReview,
    StoryboardScene)
from marketing_video.composer import compose_video, load_composition_sources, _run


class ComposerTests(unittest.TestCase):
    def sources(self,root,ready=True):
        ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        run=root/'recording'; (run/'clips').mkdir(parents=True); (run/'posters').mkdir()
        clip=run/'clips/demo.mp4'
        _run([ffmpeg,'-y','-loglevel','error','-f','lavfi','-i','color=c=0x101820:s=1280x720:r=30:d=2',
              '-c:v','libx264','-pix_fmt','yuv420p',str(clip)],'fixture video')
        Image.new('RGB',(1280,720),(14,20,28)).save(run/'posters/demo.png')
        def scene(scene_id,kind,evidence=None,flow='',step=-1):
            return StoryboardScene(id=scene_id,scene_type=kind,duration_seconds=2,headline='Useful product',
                voiceover='A concise narration.',caption='Concise caption',visual_direction='Show product',
                evidence_ids=evidence or [],flow_id=flow,step_index=step)
        board=Storyboard(status='ready',source_manifest=str(root/'manifest.json'),source_plan=str(root/'plan.json'),
            source_validation=str(root/'validation.json'),source_discovery=str(root/'discovery.json'),model='fixture',
            product_name='Fixture Product',product_type='tool',audience='Teams',language='en',tone='clear',
            total_duration_seconds=8,scenes=[scene('hook','hook',['product']),
                scene('benefit','benefit',['claim:0']),scene('demo','demo',['step:flow:1'],'flow',1),scene('cta','cta')],
            review=StoryboardReview(approved=True))
        board_path=root/'storyboard.json'; board_path.write_text(board.model_dump_json(indent=2),encoding='utf-8')
        manifest=RecordingManifest(status='ready' if ready else 'failed',source_storyboard=str(board_path.resolve()),
            source_plan=str(root/'plan.json'),source_validation=str(root/'validation.json'),site_url='https://fixture.test',
            viewport={'width':1280,'height':720},clips=[RecordedClip(scene_id='demo',flow_id='flow',step_index=1,
                status='recorded',duration_seconds=2,clip_video='clips/demo.mp4',poster='posters/demo.png')],
            narrative_scene_ids=['hook','benefit','cta'])
        recording_path=run/'recording-manifest.json'
        recording_path.write_text(manifest.model_dump_json(indent=2),encoding='utf-8')
        return board_path,recording_path

    def test_rejects_failed_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            board,recording=self.sources(Path(directory),ready=False)
            with self.assertRaisesRegex(ValueError,'not ready'):
                load_composition_sources(board,recording)

    def test_composes_video_audio_subtitles_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); board,recording=self.sources(root)
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            async def fake_tts(text,voice,target,retries=2):
                _run([ffmpeg,'-y','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.5',
                      '-c:a','libmp3lame',str(target)],'fixture tts')
            with patch('marketing_video.composer._tts',side_effect=fake_tts):
                result=asyncio.run(compose_video(board,recording,root/'output','en-US-JennyNeural'))
            self.assertEqual(result.status,'ready',result.errors)
            self.assertEqual(len(result.scenes),4)
            self.assertAlmostEqual(result.total_duration_seconds,8,places=1)
            self.assertGreater((root/'output'/result.output_video).stat().st_size,5000)
            self.assertIn('A concise narration.',(root/'output'/result.subtitles).read_text(encoding='utf-8-sig'))
            self.assertTrue((root/'output/video-manifest.json').is_file())


if __name__=='__main__':
    unittest.main()
