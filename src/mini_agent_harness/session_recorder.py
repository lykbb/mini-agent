from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
from typing import Any

from mini_agent_harness.config import Settings


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class SessionRecorder:
    path: Path
    data: dict[str, Any]

    @classmethod
    def start(
        cls,
        root: Path,
        *,
        command: str,
        settings: Settings,
        max_steps: int,
        verbose: bool,
        require_approval: bool,
    ) -> "SessionRecorder":
        session_date = datetime.now().astimezone().strftime("%Y-%m-%d")
        sessions_dir = root / "src" / "conversations"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        sequence = _next_sequence(sessions_dir, session_date)
        session_id = f"{session_date}-{sequence:03d}"
        path = sessions_dir / f"{session_id}.json"
        timestamp = utc_now()
        recorder = cls(
            path=path,
            data={
                "session_id": session_id,
                "started_at": timestamp,
                "updated_at": timestamp,
                "cwd": str(root),
                "command": command,
                "model": {
                    "name": settings.model_name,
                    "base_url": settings.openai_base_url,
                },
                "settings": {
                    "max_steps": max_steps,
                    "verbose": verbose,
                    "require_approval": require_approval,
                },
                "turns": [],
            },
        )
        recorder.save()
        return recorder

    def record_turn(self, *, user: str, assistant: str | None = None, error: str | None = None) -> None:
        timestamp = utc_now()
        turns = self.data["turns"]
        turns.append(
            {
                "index": len(turns) + 1,
                "created_at": timestamp,
                "user": user,
                "assistant": assistant,
                "error": error,
            }
        )
        self.data["updated_at"] = timestamp
        self.save()

    def model_history(self, max_turns: int | None = None) -> list[dict[str, str]]:
        turns = self.data["turns"]
        if max_turns is not None:
            turns = turns[-max_turns:]

        messages: list[dict[str, str]] = []
        for turn in turns:
            user = turn.get("user")
            assistant = turn.get("assistant")
            if not isinstance(user, str) or not isinstance(assistant, str):
                continue
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        return messages

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _next_sequence(sessions_dir: Path, session_date: str) -> int:
    pattern = re.compile(rf"^{re.escape(session_date)}-(\d{{3}})\.json$")
    highest = 0
    for path in sessions_dir.glob(f"{session_date}-*.json"):
        match = pattern.match(path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1
