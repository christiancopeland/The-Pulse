"""
Collection Scheduler for The Pulse.

Manages scheduled execution of all collectors with configurable intervals,
health monitoring, and graceful error handling.

Phase 5: Added WebSocket event broadcasting for real-time status updates.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
import logging

from .base import BaseCollector
from app.models.news_item import CollectionRun
from app.services.broadcast import (
    emit_collection_started,
    emit_collection_progress,
    emit_collection_completed,
    emit_collection_failed,
    emit_system_status,
)

logger = logging.getLogger(__name__)


class CollectionScheduler:
    """
    Manage scheduled execution of all collectors.

    Features:
    - Configurable intervals per collector
    - Concurrent or sequential execution
    - Health monitoring and status reporting
    - Graceful start/stop
    - Manual trigger support
    """

    def __init__(self, db_session_factory=None):
        """
        Initialize collection scheduler.

        Args:
            db_session_factory: Async callable that returns a database session.
                              If None, collectors run without DB persistence.
        """
        self.collectors: Dict[str, BaseCollector] = {}
        self.schedules: Dict[str, timedelta] = {}
        self.is_running = False
        self._tasks: List[asyncio.Task] = []
        self._db_session_factory = db_session_factory
        self._logger = logging.getLogger("scheduler")

    def register(
        self,
        collector: BaseCollector,
        interval: timedelta,
        run_immediately: bool = True,
    ):
        """
        Register a collector with its run interval.

        Args:
            collector: Collector instance to register
            interval: How often to run this collector
            run_immediately: Whether to run on first schedule start
        """
        self.collectors[collector.name] = collector
        self.schedules[collector.name] = interval
        self._logger.info(
            f"Registered collector: {collector.name} (every {interval})"
        )

    def unregister(self, name: str):
        """Remove a collector from the schedule."""
        if name in self.collectors:
            del self.collectors[name]
            del self.schedules[name]
            self._logger.info(f"Unregistered collector: {name}")

    async def start(self):
        """Start all scheduled collectors."""
        if self.is_running:
            self._logger.warning("Scheduler already running")
            return

        self.is_running = True
        self._logger.info(
            f"Starting collection scheduler with {len(self.collectors)} collectors"
        )

        for name, collector in self.collectors.items():
            interval = self.schedules[name]
            task = asyncio.create_task(
                self._run_collector_loop(collector, interval),
                name=f"collector_{name}"
            )
            self._tasks.append(task)

        self._logger.info("Collection scheduler started")

    async def stop(self, timeout: float = 30.0):
        """
        Stop all collectors gracefully.

        Args:
            timeout: Maximum seconds to wait for collectors to finish
        """
        if not self.is_running:
            return

        self._logger.info("Stopping collection scheduler...")
        self.is_running = False

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=timeout)

        self._tasks.clear()
        self._logger.info("Collection scheduler stopped")

    async def _run_collector_loop(
        self,
        collector: BaseCollector,
        interval: timedelta,
    ):
        """Run a single collector on schedule."""
        # Run immediately on start
        await self._run_collector_once(collector)

        while self.is_running:
            try:
                # Wait for next interval
                await asyncio.sleep(interval.total_seconds())

                if not self.is_running:
                    break

                await self._run_collector_once(collector)

            except asyncio.CancelledError:
                self._logger.debug(f"Collector {collector.name} loop cancelled")
                break
            except Exception as e:
                self._logger.error(
                    f"Unexpected error in {collector.name} loop: {e}",
                    exc_info=True
                )
                # Continue running, but wait before retry
                await asyncio.sleep(60)

    async def _run_collector_once(self, collector: BaseCollector) -> CollectionRun:
        """Execute a single collection run with event broadcasting."""
        db_session = None
        start_time = datetime.now(timezone.utc)

        self._logger.info(
            f"[SCHEDULER] Starting collection: collector={collector.name}, "
            f"source_type={collector.source_type}"
        )

        try:
            # Broadcast collection started
            await emit_collection_started(
                collector_name=collector.name,
                source_type=collector.source_type,
            )

            if self._db_session_factory:
                db_session = await self._db_session_factory()
                self._logger.debug(f"[SCHEDULER] DB session acquired for {collector.name}")

            run = await collector.run(db_session=db_session)

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Broadcast collection completed
            await emit_collection_completed(
                collector_name=collector.name,
                run_id=str(run.id) if run else "unknown",
                items_collected=run.items_collected if run else 0,
                items_new=run.items_new if run else 0,
                items_duplicate=run.items_duplicate if run else 0,
                duration_seconds=duration,
            )

            self._logger.info(
                f"[SCHEDULER] Collection finished: collector={collector.name}, "
                f"run_id={run.id if run else 'N/A'}, duration={duration:.2f}s, "
                f"new={run.items_new if run else 0}, dupes={run.items_duplicate if run else 0}"
            )

            return run

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self._logger.error(
                f"[SCHEDULER] Collection FAILED: collector={collector.name}, "
                f"duration={duration:.2f}s, error={e}",
                exc_info=True
            )

            # Broadcast collection failed
            await emit_collection_failed(
                collector_name=collector.name,
                error=str(e),
            )
            raise

        finally:
            if db_session:
                await db_session.close()
                self._logger.debug(f"[SCHEDULER] DB session closed for {collector.name}")

    async def run_all_now(self) -> List[CollectionRun]:
        """
        Trigger all collectors immediately.

        Returns:
            List of CollectionRun results
        """
        self._logger.info("Running all collectors immediately")
        results = []

        for collector in self.collectors.values():
            try:
                run = await self._run_collector_once(collector)
                results.append(run)
            except Exception as e:
                self._logger.error(f"Collector {collector.name} failed: {e}")

        return results

    async def run_collector_now(self, name: str) -> Optional[CollectionRun]:
        """
        Trigger a specific collector immediately.

        Args:
            name: Name of collector to run

        Returns:
            CollectionRun result or None if collector not found
        """
        collector = self.collectors.get(name)
        if not collector:
            self._logger.warning(f"Collector not found: {name}")
            return None

        self._logger.info(f"Running collector immediately: {name}")
        return await self._run_collector_once(collector)

    def get_status(self) -> Dict[str, Any]:
        """Get status of all collectors."""
        return {
            "is_running": self.is_running,
            "collector_count": len(self.collectors),
            "collectors": [c.get_status() for c in self.collectors.values()],
        }

    def get_collector_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific collector."""
        collector = self.collectors.get(name)
        if collector:
            return collector.get_status()
        return None

    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary."""
        statuses = [c.get_status() for c in self.collectors.values()]

        healthy = sum(1 for s in statuses if s["health"] == "healthy")
        degraded = sum(1 for s in statuses if s["health"] == "degraded")
        unhealthy = sum(1 for s in statuses if s["health"] == "unhealthy")

        if unhealthy > 0:
            overall = "unhealthy"
        elif degraded > 0:
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "overall": overall,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "total": len(statuses),
            "is_running": self.is_running,
        }


# Singleton scheduler instance
_scheduler: Optional[CollectionScheduler] = None


def get_scheduler() -> CollectionScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = CollectionScheduler()
    return _scheduler


async def setup_scheduler(db_session_factory=None) -> CollectionScheduler:
    """
    Initialize and configure the global scheduler.

    Args:
        db_session_factory: Async callable that returns a database session

    Returns:
        Configured scheduler instance (not started)
    """
    from . import get_all_collectors

    global _scheduler
    _scheduler = CollectionScheduler(db_session_factory=db_session_factory)

    # Register all collectors with default intervals
    intervals = {
        "RSS Feeds": timedelta(minutes=30),
        "GDELT": timedelta(hours=1),
        "ArXiv": timedelta(hours=2),
        "Reddit": timedelta(hours=1),
        "Local News": timedelta(minutes=30),
        "RC Manufacturers": timedelta(hours=4),
    }

    for collector in get_all_collectors():
        interval = intervals.get(collector.name, timedelta(hours=1))
        _scheduler.register(collector, interval)

    return _scheduler
