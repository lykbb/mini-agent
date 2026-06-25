from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mini_agent_harness.agent import Agent
from mini_agent_harness.config import load_settings
from mini_agent_harness.main import parse_args
from mini_agent_harness.model_client import ModelResponse, ToolCall
from mini_agent_harness.session_recorder import SessionRecorder
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


class NativeToolCallingClient:
    def __init__(self) -> None:
        self.calls = 0
        self.second_messages = None
        self.first_tools = None

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            self.first_tools = tools
            return ModelResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="read_file",
                        arguments={"path": "note.txt"},
                    )
                ],
                raw_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path": "note.txt"}'},
                        }
                    ],
                },
            )

        self.second_messages = messages
        return ModelResponse(
            content="The note says hello.",
            tool_calls=[],
            raw_message={"role": "assistant", "content": "The note says hello."},
        )


class InspectingClient:
    def __init__(self) -> None:
        self.last_messages = None
        self.last_tools = None

    def chat(self, messages, tools=None):
        self.last_messages = messages
        self.last_tools = tools
        return ModelResponse(
            content="I remember it.",
            tool_calls=[],
            raw_message={"role": "assistant", "content": "I remember it."},
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


class ConfigTests(unittest.TestCase):
    def test_load_settings_reads_dotenv_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv = Path(temp_dir) / ".env"
            dotenv.write_text(
                "\n".join(
                    [
                        "OPENAI_API_KEY=test-key",
                        "OPENAI_BASE_URL=https://example.test/v1",
                        "MODEL_NAME=test-model",
                        "TEMPERATURE=0.2",
                        "MAX_TOKENS=123",
                    ]
                ),
                encoding="utf-8",
            )

            settings = load_settings(dotenv)

            self.assertTrue(settings.has_api_key)
            self.assertEqual(settings.openai_base_url, "https://example.test/v1")
            self.assertEqual(settings.model_name, "test-model")
            self.assertEqual(settings.temperature, 0.2)
            self.assertEqual(settings.max_tokens, 123)


class SessionRecorderTests(unittest.TestCase):
    def test_records_session_turns_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = load_settings(root / "missing.env")
            recorder = SessionRecorder.start(
                root,
                command="minicode",
                settings=settings,
                max_steps=5,
                verbose=False,
                require_approval=True,
            )

            recorder.record_turn(user="你好", assistant="你好呀")

            content = recorder.path.read_text(encoding="utf-8")
            self.assertIn('"command": "minicode"', content)
            self.assertIn('"user": "你好"', content)
            self.assertIn('"assistant": "你好呀"', content)
            self.assertNotIn("OPENAI_API_KEY", content)

    def test_session_file_uses_date_and_sequence_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = load_settings(root / "missing.env")

            first = SessionRecorder.start(
                root,
                command="minicode",
                settings=settings,
                max_steps=5,
                verbose=False,
                require_approval=True,
            )
            second = SessionRecorder.start(
                root,
                command="minicode",
                settings=settings,
                max_steps=5,
                verbose=False,
                require_approval=True,
            )

            self.assertRegex(first.path.name, r"^\d{4}-\d{2}-\d{2}-001\.json$")
            self.assertRegex(second.path.name, r"^\d{4}-\d{2}-\d{2}-002\.json$")
            self.assertEqual(first.path.parent, root / "src" / "conversations")

    def test_session_model_history_contains_successful_turns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = load_settings(root / "missing.env")
            recorder = SessionRecorder.start(
                root,
                command="minicode",
                settings=settings,
                max_steps=5,
                verbose=False,
                require_approval=True,
            )

            recorder.record_turn(user="我叫 lyk", assistant="我记住了")
            recorder.record_turn(user="这轮失败", error="Agent error")

            self.assertEqual(
                recorder.model_history(),
                [
                    {"role": "user", "content": "我叫 lyk"},
                    {"role": "assistant", "content": "我记住了"},
                ],
            )


class AgentLoopTests(unittest.TestCase):
    def test_agent_sends_history_before_current_prompt(self) -> None:
        client = InspectingClient()
        agent = Agent(client=client, tools=[])

        answer = agent.run(
            "What is my name?",
            history=[
                {"role": "user", "content": "My name is lyk."},
                {"role": "assistant", "content": "Nice to meet you, lyk."},
            ],
        )

        self.assertEqual(answer, "I remember it.")
        self.assertEqual(client.last_messages[1]["content"], "My name is lyk.")
        self.assertEqual(client.last_messages[2]["content"], "Nice to meet you, lyk.")
        self.assertEqual(client.last_messages[3]["content"], "What is my name?")

    def test_agent_passes_tools_to_model(self) -> None:
        client = InspectingClient()
        agent = Agent(client=client, tools=[ReadFileTool(Path.cwd())])

        agent.run("hello")

        self.assertEqual(client.last_tools[0].name, "read_file")

    def test_agent_executes_native_tool_call_then_returns_final_answer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            (workspace / "note.txt").write_text("hello", encoding="utf-8")
            client = NativeToolCallingClient()
            agent = Agent(client=client, tools=[ReadFileTool(workspace)])

            answer = agent.run("Read note.txt and summarize it.")

            self.assertEqual(answer, "The note says hello.")
            self.assertEqual(client.calls, 2)
            self.assertEqual(client.first_tools[0].name, "read_file")
            self.assertEqual(client.second_messages[-1]["role"], "tool")
            self.assertEqual(client.second_messages[-1]["tool_call_id"], "call_1")
            self.assertIn("hello", client.second_messages[-1]["content"])

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


class CliArgumentTests(unittest.TestCase):
    def test_cli_defaults_to_approval_and_quiet_logs(self) -> None:
        args = parse_args(["hello"])

        self.assertEqual(args.prompt, ["hello"])
        self.assertFalse(args.verbose)
        self.assertFalse(args.no_approval)
        self.assertEqual(args.max_steps, 5)

    def test_cli_accepts_verbose_and_no_approval(self) -> None:
        args = parse_args(["--verbose", "--no-approval", "--max-steps", "2", "read", "file"])

        self.assertEqual(args.prompt, ["read", "file"])
        self.assertTrue(args.verbose)
        self.assertTrue(args.no_approval)
        self.assertEqual(args.max_steps, 2)

    def test_cli_prompt_is_optional_for_interactive_mode(self) -> None:
        args = parse_args([])

        self.assertEqual(args.prompt, [])
        self.assertEqual(args.max_steps, 5)

    def test_minicode_enters_agent_interface_without_prompt(self) -> None:
        args = parse_args([], prog="minicode")

        self.assertEqual(args.prompt, [])


if __name__ == "__main__":
    unittest.main()
