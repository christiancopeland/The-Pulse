"""
Collection API routes for The Pulse.

Provides endpoints for:
- Viewing collection status and health
- Manually triggering collection runs
- Viewing recent collection history
- Managing collector configuration
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging

from ....database import get_db
from ....models.news_item import NewsItem, CollectionRun
from ....services.collectors import (
    CollectionScheduler,
    get_all_collectors,
)
from ....services.collectors.scheduler import get_scheduler, setup_scheduler
from ....services.broadcast import get_broadcast_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/status")
async def get_collection_status():
    """
    Get status of all collectors.

    Returns:
        Scheduler status including all collector statuses
    """
    logger.debug("[COLLECTION] GET /status")
    try:
        scheduler = get_scheduler()
        status = scheduler.get_status()
        logger.debug(
            f"[COLLECTION] Status: running={status['is_running']}, "
            f"collectors={status['collector_count']}"
        )
        return status
    except Exception as e:
        logger.error(f"[COLLECTION] Failed to get status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get collection status: {str(e)}"
        )


@router.get("/health")
async def get_collection_health():
    """
    Get health summary of collection system.

    Returns:
        Overall health status and counts by health level
    """
    logger.debug("[COLLECTION] GET /health")
    try:
        scheduler = get_scheduler()
        health = scheduler.get_health_summary()
        logger.info(
            f"[COLLECTION] Health: overall={health['overall']}, "
            f"healthy={health['healthy']}, degraded={health['degraded']}, unhealthy={health['unhealthy']}"
        )
        return health
    except Exception as e:
        logger.error(f"[COLLECTION] Failed to get health summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health summary: {str(e)}"
        )


@router.post("/run")
async def trigger_collection(
    background_tasks: BackgroundTasks,
    collector_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger collection.

    Args:
        collector_name: Optional specific collector to run.
                       If not provided, runs all collectors.

    Returns:
        Status message indicating collection was triggered
    """
    logger.info(f"[COLLECTION] POST /run: collector={collector_name or 'all'}")

    try:
        scheduler = get_scheduler()

        if collector_name:
            # Run specific collector
            if collector_name not in scheduler.collectors:
                logger.warning(f"[COLLECTION] Collector not found: {collector_name}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Collector '{collector_name}' not found. "
                           f"Available: {list(scheduler.collectors.keys())}"
                )

            # Run in background
            async def run_collector():
                logger.info(f"[COLLECTION] Background task starting: {collector_name}")
                result = await scheduler.run_collector_now(collector_name)
                logger.info(
                    f"[COLLECTION] Background task completed: {collector_name}, "
                    f"new={result.items_new if result else 0}"
                )

            background_tasks.add_task(run_collector)
            logger.info(f"[COLLECTION] Triggered: {collector_name}")

            return {
                "status": "triggered",
                "collector": collector_name,
                "message": f"Collection started for {collector_name}"
            }
        else:
            # Run all collectors
            async def run_all():
                logger.info("[COLLECTION] Background task starting: all collectors")
                results = await scheduler.run_all_now()
                total_new = sum(r.items_new for r in results if r)
                logger.info(
                    f"[COLLECTION] Background task completed: all collectors, "
                    f"runs={len(results)}, total_new={total_new}"
                )

            background_tasks.add_task(run_all)
            logger.info(f"[COLLECTION] Triggered: all {len(scheduler.collectors)} collectors")

            return {
                "status": "triggered",
                "collector": "all",
                "message": f"Collection started for all {len(scheduler.collectors)} collectors"
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[COLLECTION] Failed to trigger collection: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger collection: {str(e)}"
        )


@router.get("/runs")
async def get_collection_runs(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    collector_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    Get recent collection run history.

    Args:
        limit: Maximum number of runs to return (default 50)
        collector_type: Filter by collector type
        status: Filter by status (running, completed, failed)

    Returns:
        List of recent collection runs
    """
    logger.debug(
        f"[COLLECTION] GET /runs: limit={limit}, type={collector_type}, status={status}"
    )
    try:
        query = select(CollectionRun).order_by(desc(CollectionRun.started_at))

        if collector_type:
            query = query.where(CollectionRun.collector_type == collector_type)
        if status:
            query = query.where(CollectionRun.status == status)

        query = query.limit(limit)

        result = await db.execute(query)
        runs = result.scalars().all()

        logger.info(f"[COLLECTION] Returned {len(runs)} collection runs")
        return [run.to_dict() for run in runs]

    except Exception as e:
        logger.error(f"[COLLECTION] Failed to get runs: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get collection runs: {str(e)}"
        )


@router.get("/runs/{run_id}")
async def get_collection_run(
    run_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific collection run.

    Args:
        run_id: UUID of the collection run

    Returns:
        Collection run details
    """
    try:
        query = select(CollectionRun).where(CollectionRun.id == run_id)
        result = await db.execute(query)
        run = result.scalar_one_or_none()

        if not run:
            raise HTTPException(
                status_code=404,
                detail=f"Collection run {run_id} not found"
            )

        return run.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection run: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get collection run: {str(e)}"
        )


@router.get("/items")
async def get_collected_items(
    db: AsyncSession = Depends(get_db),
    limit: int = 500,
    offset: int = 0,
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    hours: Optional[int] = None,
):
    """
    Get collected items with pagination support.

    Args:
        limit: Maximum number of items to return (default 500, max 1000)
        offset: Number of items to skip for pagination
        source_type: Filter by source type (rss, gdelt, arxiv, etc.)
        category: Filter by category (geopolitics, tech_ai, research, etc.)
        hours: Optional - limit to items from the last N hours (default: no time limit)

    Returns:
        Object with items array, pagination info, and total count
    """
    from sqlalchemy import func

    try:
        # Cap limit at 1000 to prevent excessive queries
        limit = min(limit, 1000)

        # Build base query
        query = select(NewsItem).order_by(desc(NewsItem.collected_at))
        count_query = select(func.count(NewsItem.id))

        # Apply time filter only if hours is specified
        if hours is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            query = query.where(NewsItem.collected_at >= cutoff)
            count_query = count_query.where(NewsItem.collected_at >= cutoff)

        if source_type:
            query = query.where(NewsItem.source_type == source_type)
            count_query = count_query.where(NewsItem.source_type == source_type)
        if category:
            query = query.where(NewsItem.categories.contains([category]))
            count_query = count_query.where(NewsItem.categories.contains([category]))

        # Get total count for pagination
        total_result = await db.execute(count_query)
        total_count = total_result.scalar() or 0

        # Apply pagination
        query = query.offset(offset).limit(limit)

        result = await db.execute(query)
        items = result.scalars().all()

        return {
            "items": [item.to_dict() for item in items],
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(items) < total_count,
        }

    except Exception as e:
        logger.error(f"Failed to get collected items: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get collected items: {str(e)}"
        )


@router.get("/items/stats")
async def get_collection_stats(
    db: AsyncSession = Depends(get_db),
    hours: int = 24,
):
    """
    Get collection statistics.

    Args:
        hours: Number of hours to analyze

    Returns:
        Statistics about collected items by source and category
    """
    try:
        from sqlalchemy import func

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Count by source type
        source_query = (
            select(
                NewsItem.source_type,
                func.count(NewsItem.id).label('count')
            )
            .where(NewsItem.collected_at >= cutoff)
            .group_by(NewsItem.source_type)
        )
        source_result = await db.execute(source_query)
        by_source = {row.source_type: row.count for row in source_result}

        # Total count
        total_query = (
            select(func.count(NewsItem.id))
            .where(NewsItem.collected_at >= cutoff)
        )
        total_result = await db.execute(total_query)
        total = total_result.scalar() or 0

        # Recent runs
        runs_query = (
            select(CollectionRun)
            .where(CollectionRun.started_at >= cutoff)
            .order_by(desc(CollectionRun.started_at))
            .limit(10)
        )
        runs_result = await db.execute(runs_query)
        recent_runs = [run.to_dict() for run in runs_result.scalars().all()]

        return {
            "period_hours": hours,
            "total_items": total,
            "by_source": by_source,
            "recent_runs": recent_runs,
        }

    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get collection stats: {str(e)}"
        )


@router.get("/collectors")
async def list_collectors():
    """
    List all available collectors.

    Returns:
        List of collector information
    """
    try:
        collectors = get_all_collectors()
        return [
            {
                "name": c.name,
                "source_type": c.source_type,
                "class": c.__class__.__name__,
            }
            for c in collectors
        ]
    except Exception as e:
        logger.error(f"Failed to list collectors: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list collectors: {str(e)}"
        )


@router.post("/start")
async def start_scheduler(background_tasks: BackgroundTasks):
    """
    Start the collection scheduler.

    Starts background collection for all registered collectors.
    """
    logger.info("[COLLECTION] POST /start - Starting scheduler")
    try:
        scheduler = get_scheduler()

        if scheduler.is_running:
            logger.info("[COLLECTION] Scheduler already running")
            return {
                "status": "already_running",
                "message": "Scheduler is already running"
            }

        # Start in background
        async def start():
            logger.info("[COLLECTION] Background task: starting scheduler")
            await scheduler.start()
            logger.info("[COLLECTION] Scheduler started successfully")

        background_tasks.add_task(start)

        logger.info(f"[COLLECTION] Scheduler start triggered: {len(scheduler.collectors)} collectors")
        return {
            "status": "starting",
            "message": f"Starting scheduler with {len(scheduler.collectors)} collectors"
        }

    except Exception as e:
        logger.error(f"[COLLECTION] Failed to start scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start scheduler: {str(e)}"
        )


@router.post("/stop")
async def stop_scheduler():
    """
    Stop the collection scheduler.

    Gracefully stops all running collectors.
    """
    logger.info("[COLLECTION] POST /stop - Stopping scheduler")
    try:
        scheduler = get_scheduler()

        if not scheduler.is_running:
            logger.info("[COLLECTION] Scheduler not running")
            return {
                "status": "not_running",
                "message": "Scheduler is not running"
            }

        await scheduler.stop()
        logger.info("[COLLECTION] Scheduler stopped successfully")

        return {
            "status": "stopped",
            "message": "Scheduler stopped successfully"
        }

    except Exception as e:
        logger.error(f"[COLLECTION] Failed to stop scheduler: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stop scheduler: {str(e)}"
        )


@router.get("/websocket/status")
async def get_websocket_status():
    """
    Get WebSocket broadcast status.

    Returns:
        Status of the WebSocket broadcast manager including
        active connections and subscriptions.
    """
    try:
        broadcast_manager = get_broadcast_manager()
        return broadcast_manager.get_status()
    except Exception as e:
        logger.error(f"Failed to get websocket status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get websocket status: {str(e)}"
        )
