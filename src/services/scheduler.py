import logging
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class KBScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job = None

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler started.")

    def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped.")

    def schedule_sync(
        self,
        sync_func: Callable[[], Awaitable[None]],
        interval_minutes: int,
    ) -> None:
        if self._job:
            self._job.remove()
        self._job = self._scheduler.add_job(
            sync_func,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="kb_sync",
            replace_existing=True,
        )
        logger.info("KB sync scheduled every %d minute(s).", interval_minutes)

    def cancel_sync(self) -> None:
        if self._job:
            self._job.remove()
            self._job = None
            logger.info("KB sync job cancelled.")
