"""The save panel must display its result before the user closes the window."""
import unittest
from playwright.async_api import async_playwright
from marketing_video.auth import SAVE_PANEL_SCRIPT


class SavePanelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        await self.page.set_content('<h1>Demo app</h1>')

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()

    async def test_success_waits_for_explicit_close(self):
        finished = []
        await self.page.expose_function('__saveDemoSession',lambda:{'ok':True,'message':'Saved','path':'D:/demo/.auth/state.json'})
        await self.page.expose_function('__finishDemoSession',lambda:finished.append(True))
        await self.page.evaluate(SAVE_PANEL_SCRIPT)
        await self.page.locator('#demo-session-save').click()
        await self.page.wait_for_function("document.getElementById('demo-session-status').textContent.includes('state.json')")
        self.assertFalse(self.page.is_closed())
        self.assertFalse(finished)
        self.assertTrue(await self.page.locator('#demo-session-close').is_visible())
        await self.page.locator('#demo-session-close').click()
        self.assertEqual(finished,[True])

    async def test_write_error_is_visible_and_retryable(self):
        def fail():
            raise RuntimeError('Simulated write failure')
        await self.page.expose_function('__saveDemoSession',fail)
        await self.page.evaluate(SAVE_PANEL_SCRIPT)
        await self.page.locator('#demo-session-save').click()
        await self.page.wait_for_function("document.getElementById('demo-session-status').textContent.includes('Simulated write failure')")
        self.assertTrue(await self.page.locator('#demo-session-save').is_enabled())
        self.assertFalse(await self.page.locator('#demo-session-close').is_visible())

    async def test_missing_process_connection_is_reported(self):
        await self.page.evaluate(SAVE_PANEL_SCRIPT)
        await self.page.locator('#demo-session-save').click()
        self.assertIn('Mất kết nối',await self.page.locator('#demo-session-status').inner_text())
        self.assertTrue(await self.page.locator('#demo-session-save').is_enabled())
