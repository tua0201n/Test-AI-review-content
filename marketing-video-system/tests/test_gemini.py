"""Gemini wiring tests without sending requests or using a real API key."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from pydantic import SecretStr
from marketing_video.settings import Settings
from marketing_video.llm import Planner
from marketing_video.models import ExplorationPlan
from browser_use.llm.views import ChatInvokeCompletion


class GeminiTests(unittest.TestCase):
    def test_missing_gemini_key_is_clear(self):
        with self.assertRaisesRegex(ValueError, "GOOGLE_API_KEY"):
            Planner(Settings(provider="google", google_api_key=SecretStr("")))

    def test_gemini_adapter_and_structured_response(self):
        settings = Settings(provider="google", model="gemini-3.5-flash-lite", google_api_key=SecretStr("test-placeholder"))
        planner = Planner(settings)
        self.assertEqual(planner.llm.provider, "google")
        self.assertEqual(planner.llm.model, settings.model)
        self.assertEqual(planner.llm.api_key, "test-placeholder")
        expected = ExplorationPlan(page_purpose="Test", probes=[], priority_urls=[])
        planner.llm.ainvoke = AsyncMock(return_value=ChatInvokeCompletion(completion=expected, usage=None))
        actual = asyncio.run(planner.invoke("Select probes", {"title":"Test"}, ExplorationPlan))
        self.assertEqual(actual, expected)
        self.assertEqual(planner.llm.ainvoke.call_args.kwargs["output_format"], ExplorationPlan)
        self.assertNotIn("test-placeholder", planner.llm.ainvoke.call_args.args[0][1].content)

    def test_configuration_limits(self):
        with self.assertRaises(ValueError):
            Settings(max_pages=200)


class RetryTests(unittest.TestCase):
    def planner(self):
        return Planner(Settings(provider='google', model='gemini-3.5-flash-lite', google_api_key=SecretStr('test-placeholder')))

    def test_transient_error_then_success(self):
        class BusyError(Exception):
            code = 503
        planner = self.planner()
        expected = ExplorationPlan(page_purpose='Recovered')
        planner.llm.ainvoke = AsyncMock(side_effect=[BusyError('busy'), ChatInvokeCompletion(completion=expected, usage=None)])
        with patch('marketing_video.llm.asyncio.sleep', new_callable=AsyncMock):
            self.assertEqual(asyncio.run(planner.invoke('test', {}, ExplorationPlan)), expected)
        self.assertEqual(planner.llm.ainvoke.await_count, 2)

    def test_retries_are_bounded(self):
        planner = self.planner()
        planner.llm.ainvoke = AsyncMock(side_effect=TimeoutError())
        with patch('marketing_video.llm.asyncio.sleep', new_callable=AsyncMock):
            with self.assertRaises(TimeoutError):
                asyncio.run(planner.invoke('test', {}, ExplorationPlan))
        self.assertEqual(planner.llm.ainvoke.await_count, 3)

    def test_non_transient_error_is_not_retried(self):
        planner = self.planner()
        planner.llm.ainvoke = AsyncMock(side_effect=ValueError('bad schema'))
        with self.assertRaises(ValueError):
            asyncio.run(planner.invoke('test', {}, ExplorationPlan))
        self.assertEqual(planner.llm.ainvoke.await_count, 1)
