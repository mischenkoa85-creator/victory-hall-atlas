"""Bounded source invariants for this additive Atlas integration (no network)."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]
BASE='0bdf99401e2d572afe6cec2cc4a846cdf202b2f0'
TAG=b'<script src="reports/panel.js" data-reporting-base="https://srv1208299.hstgr.cloud/block8-reporting/v1/reports/" defer></script>\n'

class SourceTests(unittest.TestCase):
    def test_only_script_tag_added_to_original_model(self):
        original=subprocess.check_output(['git','show',BASE+':index.html'],cwd=ROOT)
        current=(ROOT/'index.html').read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(current.count(TAG),1)
        self.assertEqual(current.replace(TAG,b'').rstrip(b'\n'),original.replace(b'\r\n',b'\n').rstrip(b'\n'))
        subprocess.run(['git','diff','--exit-code',BASE,'--','m','d'],cwd=ROOT,check=True,capture_output=True)

    def test_launcher_is_menu_only_and_no_model_mutator(self):
        panel=(ROOT/'reports/panel.js').read_text(encoding='utf-8')
        self.assertIn("document.getElementById('engbody')",panel)
        self.assertIn('menuMount.prepend(menu)',panel)
        self.assertNotIn('class="launch"',panel)
        self.assertNotIn('.launch{position:fixed',panel)
        self.assertNotIn('__A3',panel)
        self.assertNotIn('P00.',panel)

    def test_no_embedded_credentials_or_outage_snapshot(self):
        panel=(ROOT/'reports/panel.js').read_text(encoding='utf-8')
        self.assertNotRegex(panel,r'(?:vhl_|#k=)[A-Za-z0-9_-]{40,}')
        self.assertNotIn('outage-data.json',panel)
        self.assertNotIn('SOURCE_INVENTORY_ONLY_NOT_EVENT_HISTORY',panel)
        self.assertNotIn('localStorage',panel)
        self.assertNotIn('sessionStorage',panel)
        self.assertIn("credentials: 'omit'",panel)

if __name__=='__main__':unittest.main(verbosity=2)
