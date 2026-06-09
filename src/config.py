import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    telegram_bot_token: str
    anthropic_api_key: str
    anthropic_model: str
    google_service_account_file: str
    database_path: str
    log_level: str


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required. Set it in .env or environment.")
    return Config(
        telegram_bot_token=token,
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        google_service_account_file=os.environ.get(
            "GOOGLE_SERVICE_ACCOUNT_FILE",
            "credentials/google-service-account.json",
        ),
        database_path=os.environ.get("DATABASE_PATH", "data/bot.db"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
