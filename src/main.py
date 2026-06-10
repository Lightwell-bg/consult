import asyncio
import logging
from datetime import datetime

from .bot.bot import create_bot, create_dispatcher
from .bot.commands import sync_bot_commands
from .config import load_config
from .db.database import init_db
from .db.repository import Repository
from .services.anthropic_client import AnthropicClient
from .services.google_sheets import GoogleSheetsClient
from .services.critical_log import purge_expired_logs, record_critical
from .services.knowledge_base import KnowledgeBase
from .services.scheduler import KBScheduler


async def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger = logging.getLogger(__name__)

    await init_db(config.database_path)
    repo = Repository(config.database_path)
    await purge_expired_logs(repo)

    sheets_client = GoogleSheetsClient(config.google_service_account_file)
    kb = KnowledgeBase(sheets_client)
    ai_client = AnthropicClient(config.anthropic_api_key, config.anthropic_model)
    scheduler = KBScheduler()

    # Initial KB sync
    spreadsheet_id = await repo.get_setting("spreadsheet_id")
    try:
        count = await kb.sync(spreadsheet_id)
        await repo.set_setting("last_kb_sync", datetime.now().isoformat())
        await repo.set_setting("kb_entry_count", str(count))
        logger.info("Initial KB sync: %d entries.", count)
    except Exception as exc:
        logger.warning(
            "Initial KB sync failed: %s. Bot will retry on first request.", exc
        )
        await record_critical(repo, "startup_sync", str(exc))

    # Set up periodic sync if configured
    sync_mode = await repo.get_setting("sync_mode", "scheduled")
    if sync_mode == "scheduled":
        interval = int(await repo.get_setting("sync_interval_minutes", "10"))

        async def _scheduled_sync() -> None:
            try:
                sid = await repo.get_setting("spreadsheet_id")
                count = await kb.sync(sid)
                await repo.set_setting("last_kb_sync", datetime.now().isoformat())
                await repo.set_setting("kb_entry_count", str(count))
            except Exception as exc:
                await record_critical(repo, "scheduled_sync", str(exc))

        scheduler.schedule_sync(_scheduled_sync, interval)
        scheduler.start()

    bot = create_bot(config.telegram_bot_token)
    dp = create_dispatcher(repo)

    await sync_bot_commands(bot, repo)

    # Remove webhook if set (e.g. from a previous deploy) — polling requires no webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook cleared, starting polling...")

    try:
        await dp.start_polling(
            bot,
            repo=repo,
            kb=kb,
            ai_client=ai_client,
            scheduler=scheduler,
        )
    finally:
        scheduler.stop()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
