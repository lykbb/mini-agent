from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent_harness.model_client import OpenAICompatibleClient, ToolCall
from mini_agent_harness.tool import Tool
from mini_agent_harness.tools import ToolExecutionError


DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful mini agent. Use the available tools when they are useful. "
    "The application will provide tool definitions through the model API. "
    "After a tool result is provided, answer the user clearly and concisely."
)


class AgentError(RuntimeError):
    pass


ApprovalCallback = Callable[[ToolCall], bool]


@dataclass
class Agent:
    client: OpenAICompatibleClient
    tools: list[Tool]
    max_steps: int = 5
    verbose: bool = False
    require_approval: bool = False
    approval_callback: ApprovalCallback | None = None
    tool_result_preview_chars: int = 500
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    def run(self, prompt: str, history: list[dict[str, Any]] | None = None) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        self._log("Agent loop started")
        for step in range(1, self.max_steps + 1):
            self._log(f"Step {step}: asking model")
            response = self.client.chat(messages, tools=self.tools)
            manual_tool_call = self._parse_manual_tool_call(response.content)
            if not response.tool_calls and manual_tool_call is None:
                self._log("Model returned final answer")
                return response.content or ""

            messages.append(response.raw_message)
            if manual_tool_call is not None:
                self._log_tool_call(manual_tool_call)
                messages.append(self._run_manual_tool_call(manual_tool_call))
                continue

            for tool_call in response.tool_calls:
                self._log_tool_call(tool_call)
                messages.append(self._run_tool_call(tool_call))

        raise AgentError("Agent stopped because it reached the max step limit.")

    def _run_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        if not tool_call.id:
            raise AgentError(f"Tool call for {tool_call.name} did not include an id.")

        tool = self._find_tool(tool_call.name)
        if not self._tool_call_approved(tool_call):
            content = f"Tool {tool_call.name} was denied by the user."
            self._log_tool_result(tool_call.name, content)
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": content,
            }

        try:
            content = tool.run(tool_call.arguments)
        except ToolExecutionError as exc:
            content = f"Tool {tool_call.name} failed: {exc}"

        self._log_tool_result(tool_call.name, content)
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": content,
        }

    def _run_manual_tool_call(self, tool_call: ToolCall) -> dict[str, Any]:
        tool = self._find_tool(tool_call.name)
        if not self._tool_call_approved(tool_call):
            content = f"Tool {tool_call.name} was denied by the user."
            self._log_tool_result(tool_call.name, content)
            return self._manual_tool_result_message(tool_call.name, content)

        try:
            content = tool.run(tool_call.arguments)
        except ToolExecutionError as exc:
            content = f"Tool {tool_call.name} failed: {exc}"

        self._log_tool_result(tool_call.name, content)
        return self._manual_tool_result_message(tool_call.name, content)

    def _manual_tool_result_message(self, tool_name: str, content: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": (
                f"Tool result for {tool_name}:\n"
                f"{content}\n\n"
                "Use this tool result to answer the original user request. "
                "If more information is needed, you may request another tool with JSON."
            ),
        }

    def _parse_manual_tool_call(self, content: str | None) -> ToolCall | None:
        if not content:
            return None

        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        tool_name = payload.get("tool")
        arguments = payload.get("arguments")
        if not isinstance(tool_name, str) or not isinstance(arguments, dict):
            return None

        return ToolCall(id="", name=tool_name, arguments=arguments)

    def _find_tool(self, name: str) -> Tool:
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise AgentError(f"Model requested an unknown tool: {name}")

    def _tool_call_approved(self, tool_call: ToolCall) -> bool:
        if not self.require_approval:
            return True
        if self.approval_callback is None:
            self._log(f"Tool denied because no approval callback is configured: {tool_call.name}")
            return False
        approved = self.approval_callback(tool_call)
        self._log(f"Tool approval for {tool_call.name}: {'approved' if approved else 'denied'}")
        return approved

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[agent] {message}")

    def _log_tool_call(self, tool_call: ToolCall) -> None:
        arguments = json.dumps(tool_call.arguments, ensure_ascii=False)
        self._log(f"Model requested tool: {tool_call.name}({arguments})")

    def _log_tool_result(self, tool_name: str, content: str) -> None:
        preview = self._preview(content)
        self._log(f"Tool result from {tool_name}: {preview}")

    def _preview(self, content: str) -> str:
        compact = content.replace("\n", "\\n")
        if len(compact) > self.tool_result_preview_chars:
            return compact[: self.tool_result_preview_chars] + "...[truncated]"
        return compact
