import sys
from pathlib import Path

from mini_agent_harness.agent import Agent, AgentError
from mini_agent_harness.config import load_settings
from mini_agent_harness.model_client import ModelClientError, OpenAICompatibleClient, ToolCall
from mini_agent_harness.tools import get_default_tools


def confirm_tool_call(tool_call: ToolCall) -> bool:
    print("Agent wants to run a tool:")
    print(f"  tool: {tool_call.name}")
    print(f"  arguments: {tool_call.arguments}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer == "y"


def main() -> None:
    print("Agent started")
    settings = load_settings()
    print(f"Model: {settings.model_name}")
    print(f"Base URL: {settings.openai_base_url}")
    print(f"API key configured: {settings.has_api_key}")

    if len(sys.argv) < 2:
        print("Usage: mini-agent '<your prompt>'")
        return

    prompt = " ".join(sys.argv[1:])
    client = OpenAICompatibleClient(settings)
    tools = get_default_tools(Path.cwd())
    agent = Agent(
        client=client,
        tools=tools,
        verbose=True,
        require_approval=True,
        approval_callback=confirm_tool_call,
    )

    try:
        answer = agent.run(prompt)
    except (AgentError, ModelClientError) as exc:
        print(f"Agent error: {exc}")
        return

    print(answer)


if __name__ == "__main__":
    main()
