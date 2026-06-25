import argparse
import sys
from pathlib import Path

from mini_agent_harness.agent import Agent, AgentError
from mini_agent_harness.config import load_settings
from mini_agent_harness.model_client import ModelClientError, OpenAICompatibleClient, ToolCall
from mini_agent_harness.session_recorder import SessionRecorder
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
    parser.add_argument("prompt", nargs="*", help="The prompt to send to the agent.")
    return parser.parse_args(argv)


def confirm_tool_call(tool_call: ToolCall) -> bool:
    print("Agent wants to run a tool:")
    print(f"  tool: {tool_call.name}")
    print(f"  arguments: {tool_call.arguments}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer == "y"


def build_agent(args: argparse.Namespace, settings=None) -> Agent:
    print("Agent started")
    settings = settings or load_settings()
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


def run_once(
    agent: Agent,
    prompt: str,
    history: list[dict[str, str]] | None = None,
) -> tuple[str | None, str | None]:
    try:
        answer = agent.run(prompt, history=history)
    except (AgentError, ModelClientError) as exc:
        error = f"Agent error: {exc}"
        print(error)
        return None, error

    print(answer)
    return answer, None


def run_interactive(agent: Agent, recorder: SessionRecorder | None = None, *, prompt_label: str = "mini-agent") -> None:
    print("Enter a prompt. Type /exit or /quit to stop.")
    while True:
        try:
            prompt = input(f"{prompt_label}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not prompt:
            continue
        if prompt in {"/exit", "/quit"}:
            return

        history = recorder.model_history() if recorder is not None else None
        answer, error = run_once(agent, prompt, history=history)
        if recorder is not None:
            recorder.record_turn(user=prompt, assistant=answer, error=error)


def run_cli(argv: list[str] | None = None, *, prog: str = "mini-agent") -> None:
    args = parse_args(argv, prog=prog)
    settings = load_settings()
    agent = build_agent(args, settings)
    prompt = " ".join(args.prompt)
    if prompt:
        run_once(agent, prompt)
        return

    recorder = SessionRecorder.start(
        Path.cwd(),
        command=prog,
        settings=settings,
        max_steps=args.max_steps,
        verbose=args.verbose,
        require_approval=not args.no_approval,
    )
    print(f"Session log: {recorder.path}")
    run_interactive(agent, recorder, prompt_label=prog)


def main(argv: list[str] | None = None) -> None:
    run_cli(argv, prog="mini-agent")


def minicode_main(argv: list[str] | None = None) -> None:
    run_cli(argv, prog="minicode")


if __name__ == "__main__":
    main(sys.argv[1:])
