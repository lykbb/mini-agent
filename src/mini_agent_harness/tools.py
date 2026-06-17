from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mini_agent_harness.tool import Tool


class ToolExecutionError(RuntimeError):
    pass


@dataclass
class ReadFileTool(Tool):
    workspace_root: Path
    max_chars: int = 12_000

    name = "read_file"
    description = "Read a UTF-8 text file from inside the project workspace."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "A file path inside the project workspace, such as README.md.",
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ToolExecutionError("read_file requires a non-empty string path.")

        workspace_root = self.workspace_root.resolve()
        requested_path = Path(raw_path)
        if requested_path.is_absolute():
            file_path = requested_path.resolve()
        else:
            file_path = (workspace_root / requested_path).resolve()

        try:
            file_path.relative_to(workspace_root)
        except ValueError as exc:
            raise ToolExecutionError("read_file can only read files inside the workspace.") from exc

        if not file_path.exists():
            raise ToolExecutionError(f"File does not exist: {raw_path}")
        if not file_path.is_file():
            raise ToolExecutionError(f"Path is not a file: {raw_path}")

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolExecutionError(f"File is not valid UTF-8 text: {raw_path}") from exc

        if len(content) > self.max_chars:
            return content[: self.max_chars] + "\n\n[Output truncated]"
        return content


@dataclass
class WebSearchTool(Tool):
    timeout_seconds: float = 10.0
    default_max_results: int = 5

    name = "web_search"
    description = "Search the web and return a compact list of result snippets with URLs."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The web search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return, from 1 to 10.",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any]) -> str:
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolExecutionError("web_search requires a non-empty string query.")

        max_results = self._coerce_max_results(arguments.get("max_results"))
        search_url = "https://api.duckduckgo.com/?" + urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
        )
        request = Request(
            search_url,
            headers={"User-Agent": "mini-agent-harness/0.1"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_text = response.read().decode("utf-8")
        except HTTPError as exc:
            raise ToolExecutionError(f"web_search returned HTTP {exc.code}.") from exc
        except URLError as exc:
            raise ToolExecutionError(f"web_search could not reach the search API: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ToolExecutionError("web_search timed out.") from exc

        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError("web_search response was not valid JSON.") from exc

        results = self._extract_results(payload, max_results)
        if not results:
            return f"No web search results found for: {query}"

        lines = [f"Web search results for: {query}"]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {result['text']}")
            if result["url"]:
                lines.append(f"   URL: {result['url']}")
        return "\n".join(lines)

    def _coerce_max_results(self, value: Any) -> int:
        if value is None:
            return self.default_max_results
        try:
            max_results = int(value)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError("max_results must be an integer.") from exc
        return min(max(max_results, 1), 10)

    def _extract_results(self, payload: dict[str, Any], max_results: int) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []

        abstract = payload.get("AbstractText")
        abstract_url = payload.get("AbstractURL")
        if isinstance(abstract, str) and abstract:
            results.append({"text": abstract, "url": abstract_url if isinstance(abstract_url, str) else ""})

        for topic in self._iter_related_topics(payload.get("RelatedTopics", [])):
            text = topic.get("Text")
            url = topic.get("FirstURL")
            if isinstance(text, str) and text:
                results.append({"text": text, "url": url if isinstance(url, str) else ""})
            if len(results) >= max_results:
                break

        return results[:max_results]

    def _iter_related_topics(self, topics: Any) -> list[dict[str, Any]]:
        if not isinstance(topics, list):
            return []

        flattened: list[dict[str, Any]] = []
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            nested_topics = topic.get("Topics")
            if isinstance(nested_topics, list):
                flattened.extend(self._iter_related_topics(nested_topics))
            else:
                flattened.append(topic)
        return flattened


def get_default_tools(workspace_root: Path) -> list[Tool]:
    return [
        ReadFileTool(workspace_root=workspace_root),
        WebSearchTool(),
    ]
