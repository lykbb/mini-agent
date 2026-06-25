from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_base_url: str
    model_name: str
    temperature: float
    max_tokens: int

    @property
    def has_api_key(self) -> bool:
        return bool(self.openai_api_key)


def load_settings(dotenv_path: Path | None = None) -> Settings:
    values = _load_dotenv_values(dotenv_path or Path.cwd() / ".env")

    return Settings(
        openai_api_key=_get_setting("OPENAI_API_KEY", values),
        openai_base_url=_get_setting("OPENAI_BASE_URL", values, "https://api.openai.com/v1"),
        model_name=_get_setting("MODEL_NAME", values, "gpt-4.1-mini"),
        temperature=float(_get_setting("TEMPERATURE", values, "0.7")),
        max_tokens=int(_get_setting("MAX_TOKENS", values, "4096")),
    )


def _get_setting(name: str, dotenv_values: dict[str, str], default: str | None = None) -> str | None:
    return os.getenv(name) or dotenv_values.get(name) or default


def _load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            values[key] = value

    return values
