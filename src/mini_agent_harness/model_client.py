from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from mini_agent_harness.config import Settings
from mini_agent_harness.tool import Tool, to_openai_tool_schema


class ModelClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    content: str | None
    tool_calls: list[ToolCall]
    raw_message: dict[str, Any]


@dataclass
class OpenAICompatibleClient:
    settings: Settings
    timeout_seconds: float = 60.0

    def complete(self, prompt: str) -> str:
        messages = [{"role": "user", "content": prompt}]
        payload = self._post_chat_completion(messages)
        message = self._get_first_message(payload)
        content = message.get("content")

        if not isinstance(content, str):
            raise ModelClientError(f"Model response content was not text. Shape: {self._payload_shape(payload)}")

        return content

    def complete_with_tools(self, prompt: str, tools: list[Tool]) -> ModelResponse:
        messages = [{"role": "user", "content": prompt}]
        return self.chat(messages, tools=tools)

    def chat(self, messages: list[dict[str, Any]], tools: list[Tool] | None = None) -> ModelResponse:
        payload = self._post_chat_completion(messages, tools=tools)
        message = self._get_first_message(payload)
        return ModelResponse(
            content=message.get("content"),
            tool_calls=self._parse_tool_calls(message.get("tool_calls", [])),
            raw_message=message,
        )

    def _post_chat_completion(
        self,
        messages: list[dict[str, Any]],
        tools: list[Tool] | None = None,
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise ModelClientError("OPENAI_API_KEY is not configured.")

        url = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        body = {
            "model": self.settings.model_name,
            "messages": messages,
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
        }
        if tools:
            body["tools"] = [to_openai_tool_schema(tool) for tool in tools]
            body["tool_choice"] = "auto"

        request = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            raise ModelClientError(f"Model API returned HTTP {exc.code}: {error_text}") from exc
        except URLError as exc:
            raise ModelClientError(f"Could not reach model API: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ModelClientError("Model API request timed out.") from exc

        try:
            return json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ModelClientError("Model API response was not valid JSON.") from exc

    def _get_first_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        api_error = payload.get("error")
        if isinstance(api_error, dict):
            message = api_error.get("message") or api_error.get("msg") or api_error
            raise ModelClientError(f"Model API returned an error: {message}")
        if isinstance(api_error, str):
            raise ModelClientError(f"Model API returned an error: {api_error}")

        choices = payload.get("choices")
        if choices is None:
            raise ModelClientError(f"Model response did not include choices. Shape: {self._payload_shape(payload)}")
        if not isinstance(choices, list):
            raise ModelClientError(f"Model response choices was not a list. Shape: {self._payload_shape(payload)}")
        if not choices:
            raise ModelClientError(
                "Model response included an empty choices list. "
                "This provider/model may not support tool calling for this request. "
                f"Shape: {self._payload_shape(payload)}"
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise ModelClientError(f"Model response choice was not an object. Shape: {self._payload_shape(payload)}")

        message = choice.get("message")
        if isinstance(message, dict):
            return message

        delta = choice.get("delta")
        if isinstance(delta, dict):
            return delta

        text = choice.get("text")
        if isinstance(text, str):
            return {"role": "assistant", "content": text}

        raise ModelClientError(f"Model response did not include a message. Shape: {self._payload_shape(payload)}")

    def _payload_shape(self, payload: dict[str, Any]) -> str:
        keys = ", ".join(sorted(payload.keys()))
        choices = payload.get("choices")
        if choices is None:
            return f"payload keys=[{keys}], choices=None"
        if not isinstance(choices, list):
            return f"payload keys=[{keys}], choices type={type(choices).__name__}"
        if isinstance(choices, list) and not choices:
            return f"payload keys=[{keys}], choices=[]"
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                choice_keys = ", ".join(sorted(first_choice.keys()))
                return f"payload keys=[{keys}], first choice keys=[{choice_keys}]"
        return f"payload keys=[{keys}]"

    def _parse_tool_calls(self, raw_tool_calls: Any) -> list[ToolCall]:
        if raw_tool_calls is None:
            return []
        if not isinstance(raw_tool_calls, list):
            raise ModelClientError("Model response tool_calls was not a list.")

        tool_calls: list[ToolCall] = []
        for raw_tool_call in raw_tool_calls:
            if not isinstance(raw_tool_call, dict):
                raise ModelClientError("Model response included an invalid tool call.")

            function = raw_tool_call.get("function")
            if not isinstance(function, dict):
                raise ModelClientError("Tool call did not include a function object.")

            name = function.get("name")
            if not isinstance(name, str) or not name:
                raise ModelClientError("Tool call did not include a function name.")

            raw_arguments = function.get("arguments", "{}")
            if not isinstance(raw_arguments, str):
                raise ModelClientError("Tool call arguments were not a JSON string.")

            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as exc:
                raise ModelClientError("Tool call arguments were not valid JSON.") from exc

            if not isinstance(arguments, dict):
                raise ModelClientError("Tool call arguments were not a JSON object.")

            tool_call_id = raw_tool_call.get("id", "")
            tool_calls.append(
                ToolCall(
                    id=tool_call_id if isinstance(tool_call_id, str) else "",
                    name=name,
                    arguments=arguments,
                )
            )

        return tool_calls
