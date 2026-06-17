from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mini_agent_harness.agent import Agent
from mini_agent_harness.model_client import ModelResponse
from mini_agent_harness.tools import ReadFileTool, ToolExecutionError


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(
                content='{"tool": "read_file", "arguments": {"path": "note.txt"}}',
                tool_calls=[],
                raw_message={
                    "role": "assistant",
                    "content": '{"tool": "read_file", "arguments": {"path": "note.txt"}}',
                },
            )

        self.last_messages = messages
        return ModelResponse(
            content="The note says hello.",
            tool_calls=[],
            raw_message={"role": "assistant", "content": "The note says hello."},
        )


class ReadFileToolTests(unittest.TestCase):
    def test_reads_file_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            note = workspace / "note.txt"
            note.write_text("hello from test", encoding="utf-8")

            tool = ReadFileTool(workspace)

            self.assertEqual(tool.run({"path": "note.txt"}), "hello from test")

    def test_rejects_file_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            outside = Path(temp_dir) / "outside.txt"
            outside.write_text("secret", encoding="utf-8")

            tool = ReadFileTool(workspace)

            with self.assertRaises(ToolExecutionError):
                tool.run({"path": "../outside.txt"})


class AgentLoopTests(unittest.TestCase):
    def test_agent_executes_manual_tool_call_then_returns_final_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "note.txt").write_text("hello", encoding="utf-8")
            client = FakeClient()
            agent = Agent(
                client=client,
                tools=[ReadFileTool(workspace)],
            )

            answer = agent.run("Read note.txt and summarize it.")

            self.assertEqual(answer, "The note says hello.")
            self.assertEqual(client.calls, 2)
            self.assertIn("Tool result for read_file", client.last_messages[-1]["content"])
            self.assertIn("hello", client.last_messages[-1]["content"])

    def test_agent_respects_denied_tool_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "note.txt").write_text("hello", encoding="utf-8")
            client = FakeClient()
            agent = Agent(
                client=client,
                tools=[ReadFileTool(workspace)],
                require_approval=True,
                approval_callback=lambda tool_call: False,
            )

            answer = agent.run("Read note.txt and summarize it.")

            self.assertEqual(answer, "The note says hello.")
            self.assertEqual(client.calls, 2)
            self.assertIn("Tool read_file was denied by the user.", client.last_messages[-1]["content"])
            self.assertNotIn("hello", client.last_messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
