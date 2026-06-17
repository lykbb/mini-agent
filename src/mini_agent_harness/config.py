from dataclasses import dataclass
import os


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


def load_settings() -> Settings:
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        model_name=os.getenv("MODEL_NAME", "gpt-4.1-mini"),
        temperature=float(os.getenv("TEMPERATURE", "0.7")),
        max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
    )
