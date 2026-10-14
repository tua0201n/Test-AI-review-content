"""Session import must preserve product auth and avoid cross-site state reuse."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from marketing_video.auth import import_session_file, session_for


class AuthTests(unittest.TestCase):
    def test_import_is_scoped_to_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'export.json'
            source.write_text(json.dumps({'cookies':[
                {'domain':'.aisoeasy.co','name':'session','value':'demo-only'},
                {'domain':'api.aisoeasy.co','name':'api_session','value':'demo-api'},
                {'domain':'.google.com','name':'other','value':'excluded'}],
                'origins':[{'origin':'https://aisoeasy.co','localStorage':[]},
                           {'origin':'https://google.com','localStorage':[]}]}),encoding='utf-8')
            target = root/'.auth'/'state.json'
            with patch('marketing_video.auth.AUTH_FILE',target):
                import_session_file(source,'https://aisoeasy.co/')
                imported = json.loads(target.read_text(encoding='utf-8'))
                self.assertEqual(len(imported['cookies']),2)
                self.assertEqual(len(imported['origins']),1)
                self.assertEqual(session_for('https://aisoeasy.co/dashboard'),str(target))
                self.assertIsNone(session_for('https://other.test/'))

    def test_import_rejects_wrong_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'export.json'
            source.write_text(json.dumps({'cookies':[{'domain':'other.test'}],'origins':[]}),encoding='utf-8')
            with patch('marketing_video.auth.AUTH_FILE',root/'.auth'/'state.json'):
                with self.assertRaisesRegex(ValueError,'no data belonging'):
                    import_session_file(source,'https://aisoeasy.co/')

    def test_missing_session_is_not_assumed_authenticated(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('marketing_video.auth.AUTH_FILE',Path(directory)/'missing.json'):
                self.assertIsNone(session_for('https://aisoeasy.co/'))
