import argparse
import sys
from pathlib import Path

from mini_agent_harness.agent import Agent, AgentError
from mini_agent_harness.config import load_settings
from mini_agent_harness.model_client import ModelClientError, OpenAICompatibleClient, ToolCall
from mini_agent_harness.tools import get_default_tools


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def parse_args(
    argv: list[str] | None = None,
    *,
    prog: str = "mini-agent",
    require_code_command: bool = False,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print agent loop logs while running.",
    )
    parser.add_argument(
        "--no-approval",
        action="store_true",
        help="Run requested tools without asking for terminal approval.",
    )
    parser.add_argument(
        "--max-steps",
        type=positive_int,
        default=5,
        help="Maximum number of model/tool loop steps before stopping.",
    )
    if require_code_command:
        parser.add_argument("command", choices=["code"], help="Start the agent chat interface.")
    parser.add_argument("prompt", nargs="*", help="The prompt to send to the agent.")
    return parser.parse_args(argv)


def confirm_tool_call(tool_call: ToolCall) -> bool:
    print("Agent wants to run a tool:")
    print(f"  tool: {tool_call.name}")
    print(f"  arguments: {tool_call.arguments}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer == "y"


def build_agent(args: argparse.Namespace) -> Agent:
    print("Agent started")
    settings = load_settings()
    print(f"Model: {settings.model_name}")
    print(f"Base URL: {settings.openai_base_url}")
    print(f"API key configured: {settings.has_api_key}")

    client = OpenAICompatibleClient(settings)
    tools = get_default_tools(Path.cwd())
    return Agent(
        client=client,
        tools=tools,
        max_steps=args.max_steps,
        verbose=args.verbose,
        require_approval=not args.no_approval,
        approval_callback=confirm_tool_call,
    )


def run_once(agent: Agent, prompt: str) -> None:
    try:
        answer = agent.run(prompt)
    except (AgentError, ModelClientError) as exc:
        print(f"Agent error: {exc}")
        return

    print(answer)


def run_interactive(agent: Agent) -> None:
    print("Enter a prompt. Type /exit or /quit to stop.")
    while True:
        try:
            prompt = input("mini-agent> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return

        run_once(agent, prompt)


def run_cli(argv: list[str] | None = None, *, prog: str = "mini-agent", require_code_command: bool = False) -> None:
    args = parse_args(argv, prog=prog, require_code_command=require_code_command)
    agent = build_agent(args)
    prompt = " ".join(args.prompt)
    if prompt:
        run_once(agent, prompt)
        return

    run_interactive(agent)


def main(argv: list[str] | None = None) -> None:
    run_cli(argv, prog="mini-agent")


def cloud_main(argv: list[str] | None = None) -> None:
    run_cli(argv, prog="cloud", require_code_command=True)


if __name__ == "__main__":
    main(sys.argv[1:])
