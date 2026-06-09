import os
import pytest

# Use a test .env so the config module doesn't fail on missing vars
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test:token")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("ANTHROPIC_MODEL", "claude-test")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials/test.json")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture
async def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    from src.db.database import init_db
    await init_db(path)
    return path


@pytest.fixture
async def repo(db_path):
    from src.db.repository import Repository
    return Repository(db_path)
