import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import claude_service


class FakeMessage:
    def __init__(self):
        self.content = [SimpleNamespace(type="text", text="Short summary.")]
        self.model = "claude-sonnet-4-6"
        self.usage = SimpleNamespace(input_tokens=12, output_tokens=9)


class FakeMessagesClient:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeMessage()


class FakeAnthropic:
    def __init__(self, **kwargs):
        self.messages = FakeMessagesClient()


class ClaudeServiceTests(unittest.TestCase):
    def test_generate_text_uses_messages_api(self):
        with patch.object(claude_service, "AsyncAnthropic", FakeAnthropic):
            service = claude_service.ClaudeService()
            result = asyncio.run(service.generate_text("My message", system="x"))

            self.assertEqual(result.text, "Short summary.")
            self.assertEqual(result.model, "claude-sonnet-4-6")
            self.assertEqual(result.input_tokens, 12)
            self.assertEqual(result.output_tokens, 9)
            self.assertIn("system", service.client.messages.calls[0])
            self.assertEqual(service.client.messages.calls[0]["messages"][0]["content"], "My message")


if __name__ == "__main__":
    unittest.main()
