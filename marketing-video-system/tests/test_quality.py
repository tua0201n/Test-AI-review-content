"""Task 6 validates media and emits a sanitized, checksummed package."""
import asyncio
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import imageio_ffmpeg
from marketing_video.composer import compose_video, _run
from marketing_video.models import ActionTrace, Checkpoint, CheckpointResult, RecordingManifest
from marketing_video.quality import parse_srt, quality_and_package
import test_composer


class QualityTests(unittest.TestCase):
    def test_rejects_malformed_subtitle_blocks(self):
        with self.assertRaisesRegex(ValueError,'Malformed'):
            parse_srt('1\nmissing timing\nCaption')

    def test_packages_only_clean_verified_deliverables(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            board,recording_path=test_composer.ComposerTests.sources(None,root)
            recording=RecordingManifest.model_validate_json(recording_path.read_text(encoding='utf-8'))
            point=Checkpoint(kind='text_contains',expected='Result')
            recording.clips[0].trace=ActionTrace(scene_id='demo',flow_id='flow',step_index=1,
                operation='click',target_label='Details',started_seconds=0,ended_seconds=2,
                cursor_from=[10,10],cursor_to=[100,100],
                checkpoints=[CheckpointResult(step_index=1,checkpoint=point,actual='[text present]',passed=True)])
            recording_path.write_text(recording.model_dump_json(indent=2),encoding='utf-8')
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            async def fake_tts(text,voice,target,retries=2):
                _run([ffmpeg,'-y','-loglevel','error','-f','lavfi','-i','sine=frequency=440:duration=0.5',
                      '-c:a','libmp3lame',str(target)],'fixture tts')
            with patch('marketing_video.composer._tts',side_effect=fake_tts):
                video=asyncio.run(compose_video(board,recording_path,root/'video','en-US-JennyNeural'))
            self.assertEqual(video.status,'ready',video.errors)
            qa,delivery=quality_and_package(root/'video/video-manifest.json',root/'qa',root/'exports')
            self.assertEqual(delivery.status,'ready',delivery.errors)
            self.assertTrue(all(check.status=='passed' for check in delivery.checks))
            archive=root/'exports'/delivery.archive
            self.assertTrue(archive.is_file())
            with zipfile.ZipFile(archive) as bundle:
                names=set(bundle.namelist())
                self.assertIn('marketing-video.mp4',names)
                self.assertIn('checksums.sha256',names)
                self.assertNotIn('.env',names)
                self.assertFalse(any('.auth' in name for name in names))
                provenance=json.loads(bundle.read('provenance.json'))
                self.assertNotIn(str(root),json.dumps(provenance))
            self.assertTrue((qa/'archive.sha256').is_file())


if __name__=='__main__':
    unittest.main()
