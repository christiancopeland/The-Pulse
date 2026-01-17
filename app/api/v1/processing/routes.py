"""
Processing API routes for The Pulse.

Provides endpoints for:
- Processing pending news items
- Validating and ranking items
- Semantic search across processed items
- Processing statistics

Phase 3 of The Pulse Integration Plan.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, or_, text, update
from typing import List, Optional, Callable
from datetime import datetime, timezone, timedelta
import logging
import os
import asyncio

from ....database import get_db
from ....models.news_item import NewsItem
from ....models.entities import TrackedEntity
from ....services.processing import (
    ProcessingPipeline,
    ContentValidator,
    RelevanceRanker,
    NewsItemEmbedder,
)
from ....services.entity_extraction import AutoEntityExtractor
from ....services.extraction_queue_manager import get_extraction_manager, ExtractionQueueManager
from ....core.dependencies import (
    get_local_user,
    LocalUser,
    LOCAL_USER_ID,
    get_wikidata_linker,
)
from ....services.entity_extraction.wikidata_linker import WikiDataLinker

router = APIRouter()
logger = logging.getLogger(__name__)


# Global pipeline instance (lazy init)
_pipeline: Optional[ProcessingPipeline] = None
_embedder: Optional[NewsItemEmbedder] = None


def get_embedder() -> NewsItemEmbedder:
    """Get or create embedder instance."""
    global _embedder
    if _embedder is None:
        api_key = os.getenv("OPENAI_API_KEY")
        _embedder = NewsItemEmbedder(openai_api_key=api_key)
    return _embedder


@router.post("/run")
async def run_processing(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    skip_validation: bool = False,
    skip_embedding: bool = False,
    user_id: Optional[str] = None,
):
    """
    Process pending news items.

    Runs the full processing pipeline on unprocessed items:
    1. Validation - Filter low-quality content
    2. Ranking - Calculate relevance scores
    3. Entity extraction - Find tracked entity mentions
    4. Relationship detection - Identify entity co-occurrences
    5. Embedding - Generate vectors for semantic search

    Args:
        limit: Maximum number of items to process (1-500)
        skip_validation: Skip validation stage
        skip_embedding: Skip embedding generation (faster)
        user_id: Optional user ID for entity filtering

    Returns:
        Processing status and task info
    """
    try:
        # Count pending items
        count_query = select(func.count(NewsItem.id)).where(NewsItem.processed == 0)
        result = await db.execute(count_query)
        pending_count = result.scalar() or 0

        if pending_count == 0:
            return {
                "status": "no_pending",
                "message": "No pending items to process",
                "pending_count": 0,
            }

        # Get API key from environment
        openai_key = os.getenv("OPENAI_API_KEY")
        enable_embedding = bool(openai_key) and not skip_embedding

        # Create pipeline
        pipeline = ProcessingPipeline(
            db_session=db,
            openai_api_key=openai_key,
            enable_embedding=enable_embedding,
        )

        # Run processing
        result = await pipeline.process_pending_items(
            limit=limit,
            user_id=user_id,
        )

        return {
            "status": "completed",
            "message": f"Processed {result.stats.validated} items",
            "pending_count": pending_count,
            "stats": result.stats.to_dict(),
        }

    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )


@router.post("/batch")
async def process_batch(
    item_ids: List[str],
    db: AsyncSession = Depends(get_db),
    skip_validation: bool = False,
    skip_embedding: bool = False,
    user_id: Optional[str] = None,
):
    """
    Process specific news items by ID.

    Args:
        item_ids: List of NewsItem UUIDs to process
        skip_validation: Skip validation stage
        skip_embedding: Skip embedding generation
        user_id: Optional user ID for entity filtering

    Returns:
        Processing results
    """
    if not item_ids:
        raise HTTPException(
            status_code=400,
            detail="No item IDs provided"
        )

    if len(item_ids) > 100:
        raise HTTPException(
            status_code=400,
            detail="Maximum 100 items per batch"
        )

    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        enable_embedding = bool(openai_key) and not skip_embedding

        pipeline = ProcessingPipeline(
            db_session=db,
            openai_api_key=openai_key,
            enable_embedding=enable_embedding,
        )

        result = await pipeline.reprocess_items(
            item_ids=item_ids,
            user_id=user_id,
        )

        return {
            "status": "completed",
            "items_requested": len(item_ids),
            "stats": result.stats.to_dict(),
            "errors": result.errors[:5] if result.errors else [],
        }

    except Exception as e:
        logger.error(f"Batch processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Batch processing failed: {str(e)}"
        )


@router.post("/validate")
async def validate_items(
    item_ids: Optional[List[str]] = None,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    strict: bool = False,
):
    """
    Validate news items (validation stage only).

    Args:
        item_ids: Specific item IDs to validate (optional)
        limit: Max items if no IDs provided
        strict: Use strict validation mode

    Returns:
        Validation results for each item
    """
    try:
        validator = ContentValidator(strict_mode=strict)

        # Get items
        if item_ids:
            import uuid
            stmt = select(NewsItem).where(
                NewsItem.id.in_([uuid.UUID(id) for id in item_ids])
            )
        else:
            stmt = select(NewsItem).order_by(
                desc(NewsItem.collected_at)
            ).limit(limit)

        result = await db.execute(stmt)
        items = list(result.scalars().all())

        if not items:
            return {"items": [], "message": "No items found"}

        # Validate
        results = await validator.validate_batch(items)

        return {
            "total": len(items),
            "valid": sum(1 for r in results.values() if r.is_valid),
            "invalid": sum(1 for r in results.values() if not r.is_valid),
            "results": {
                item_id: {
                    "is_valid": r.is_valid,
                    "score": round(r.score, 3),
                    "issues": r.issues,
                }
                for item_id, r in results.items()
            }
        }

    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        )


@router.post("/rank")
async def rank_items(
    item_ids: Optional[List[str]] = None,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Rank news items by relevance (ranking stage only).

    Args:
        item_ids: Specific item IDs to rank (optional)
        limit: Max items if no IDs provided

    Returns:
        Ranking results sorted by score
    """
    try:
        ranker = RelevanceRanker()

        # Get items
        if item_ids:
            import uuid
            stmt = select(NewsItem).where(
                NewsItem.id.in_([uuid.UUID(id) for id in item_ids])
            )
        else:
            stmt = select(NewsItem).order_by(
                desc(NewsItem.collected_at)
            ).limit(limit)

        result = await db.execute(stmt)
        items = list(result.scalars().all())

        if not items:
            return {"items": [], "message": "No items found"}

        # Rank
        results = await ranker.rank_batch(items)

        return {
            "total": len(items),
            "results": [
                {
                    "item_id": r.item_id,
                    "score": round(r.score, 3),
                    "components": {k: round(v, 3) for k, v in r.components.items()},
                    "title": r.metadata.get("source_name", ""),
                }
                for r in results
            ]
        }

    except Exception as e:
        logger.error(f"Ranking failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ranking failed: {str(e)}"
        )


@router.get("/search")
async def search_items(
    query: str = Query(..., min_length=3),
    limit: int = Query(10, ge=1, le=50),
    source_type: Optional[str] = None,
):
    """
    Semantic search across processed news items.

    Uses vector embeddings to find semantically similar items.

    Args:
        query: Search query text
        limit: Maximum results to return
        source_type: Optional filter by source type

    Returns:
        List of matching items with similarity scores
    """
    if not query.strip():
        raise HTTPException(
            status_code=400,
            detail="Query cannot be empty"
        )

    try:
        embedder = get_embedder()
        results = await embedder.search_similar(
            query=query,
            limit=limit,
            source_type=source_type,
        )

        return {
            "query": query,
            "count": len(results),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/stats")
async def get_processing_stats(
    db: AsyncSession = Depends(get_db),
    hours: int = Query(24, ge=1, le=168),
):
    """
    Get processing statistics.

    Args:
        hours: Number of hours to analyze (1-168)

    Returns:
        Statistics about processed items
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Count by processing status
        status_query = (
            select(
                NewsItem.processed,
                func.count(NewsItem.id).label('count')
            )
            .where(NewsItem.collected_at >= cutoff)
            .group_by(NewsItem.processed)
        )
        status_result = await db.execute(status_query)
        by_status = {
            row.processed: row.count
            for row in status_result
        }

        # Count with embeddings
        embedded_query = (
            select(func.count(NewsItem.id))
            .where(NewsItem.collected_at >= cutoff)
            .where(NewsItem.qdrant_id.isnot(None))
        )
        embedded_result = await db.execute(embedded_query)
        embedded_count = embedded_result.scalar() or 0

        # Average relevance score
        avg_score_query = (
            select(func.avg(NewsItem.relevance_score))
            .where(NewsItem.collected_at >= cutoff)
            .where(NewsItem.processed == 1)
        )
        avg_result = await db.execute(avg_score_query)
        avg_score = avg_result.scalar() or 0.0

        # Get Qdrant stats
        try:
            embedder = get_embedder()
            qdrant_stats = embedder.get_collection_stats()
        except Exception:
            qdrant_stats = {"error": "Qdrant not available"}

        return {
            "period_hours": hours,
            "items_by_status": {
                "pending": by_status.get(0, 0),
                "processed": by_status.get(1, 0),
                "failed": by_status.get(2, 0),
            },
            "embedded_count": embedded_count,
            "average_relevance_score": round(avg_score, 3),
            "qdrant_stats": qdrant_stats,
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


@router.get("/queue")
async def get_processing_queue(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Get items in the processing queue (pending items).

    Args:
        limit: Maximum items to return

    Returns:
        List of pending items awaiting processing
    """
    try:
        stmt = (
            select(NewsItem)
            .where(NewsItem.processed == 0)
            .order_by(desc(NewsItem.collected_at))
            .limit(limit)
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        return {
            "count": len(items),
            "items": [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "source_name": item.source_name,
                    "collected_at": item.collected_at.isoformat() if item.collected_at else None,
                }
                for item in items
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get queue: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get queue: {str(e)}"
        )


@router.delete("/embeddings/{item_id}")
async def delete_embedding(
    item_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete embedding for a specific item.

    Args:
        item_id: NewsItem UUID

    Returns:
        Deletion status
    """
    try:
        embedder = get_embedder()
        deleted = await embedder.delete_embedding(item_id)

        if deleted:
            # Clear qdrant_id from NewsItem
            import uuid
            stmt = select(NewsItem).where(NewsItem.id == uuid.UUID(item_id))
            result = await db.execute(stmt)
            item = result.scalar_one_or_none()

            if item:
                item.qdrant_id = None
                await db.commit()

            return {"status": "deleted", "item_id": item_id}
        else:
            return {"status": "not_found", "item_id": item_id}

    except Exception as e:
        logger.error(f"Failed to delete embedding: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete embedding: {str(e)}"
        )


@router.get("/extract-entities/status")
async def extraction_status():
    """
    Get current entity extraction queue status.

    Returns:
        - is_active: Whether an extraction is currently running
        - active_task: Details of current task if running
        - queue_size: Number of pending requests
        - recent_completed: Last 5 completed extractions
    """
    manager = get_extraction_manager()
    return await manager.get_status()


@router.post("/extract-entities")
async def extract_entities(
    db: AsyncSession = Depends(get_db),
    current_user: LocalUser = Depends(get_local_user),
    wikidata_linker: WikiDataLinker = Depends(get_wikidata_linker),
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    limit: int = Query(50, ge=1, le=200, description="Max items to process"),
    auto_track: bool = Query(True, description="Auto-track high-confidence entities"),
    confidence_threshold: float = Query(0.7, ge=0.3, le=1.0, description="Min confidence for auto-tracking"),
    skip_wikidata: bool = Query(False, description="Skip WikiData linking for faster processing"),
):
    """
    Extract and auto-track entities from recent news items using GLiNER NER.

    This endpoint uses zero-shot named entity recognition to discover:
    - People (PERSON)
    - Organizations (ORGANIZATION)
    - Government agencies (GOVERNMENT_AGENCY)
    - Military units (MILITARY_UNIT)
    - Locations (LOCATION)
    - Political parties (POLITICAL_PARTY)
    - Events (EVENT)

    High-confidence entities are automatically added to tracked entities.
    Only one extraction can run at a time - subsequent requests are queued.

    Args:
        hours: Time window for news items (1-168 hours)
        limit: Maximum items to process (1-200)
        auto_track: Whether to auto-track high-confidence entities
        confidence_threshold: Minimum confidence for auto-tracking (0.3-1.0)
        skip_wikidata: Skip WikiData linking for faster bulk processing

    Returns:
        Extraction statistics and newly discovered entities
    """
    manager = get_extraction_manager()

    # Check if extraction already in progress
    if await manager.is_extraction_active():
        status = await manager.get_status()
        return JSONResponse(
            status_code=202,  # Accepted but queued
            content={
                "status": "queued",
                "message": "Extraction already in progress. Your request is queued.",
                "active_task": status["active_task"],
                "queue_position": status["queue_size"] + 1,
            }
        )

    # Acquire slot and proceed
    task = await manager.acquire_slot()
    try:
        logger.info(f"Starting entity extraction: hours={hours}, limit={limit}, auto_track={auto_track}")

        # Create auto extractor - use shared WikiData linker unless skipping
        extractor = AutoEntityExtractor(
            db_session=db,
            user_id=current_user.user_id,
            wikidata_linker=None if skip_wikidata else wikidata_linker
        )

        # Progress callback for status updates
        async def update_progress(processed: int, total: int):
            await manager.update_progress(task, processed, total)

        # Run batch extraction
        result = await extractor.batch_extract_recent(
            hours=hours,
            limit=limit,
            auto_track=auto_track,
            auto_track_threshold=confidence_threshold,
            progress_callback=update_progress
        )

        await manager.release_slot(task, success=True)

        logger.info(
            f"Entity extraction complete: {result.items_processed} items, "
            f"{result.unique_entities} unique entities, "
            f"{result.new_entities_created} new entities tracked"
        )

        return {
            "status": "completed",
            "request_id": str(task.request_id),
            "stats": {
                "items_processed": result.items_processed,
                "total_entities_extracted": result.total_entities_extracted,
                "unique_entities": result.unique_entities,
                "new_entities_created": result.new_entities_created,
                "mentions_created": result.mentions_created,
                "processing_time_seconds": round(result.processing_time_seconds, 2),
            },
            "errors": result.errors[:5] if result.errors else [],
        }

    except Exception as e:
        await manager.release_slot(task, success=False, error=str(e))
        logger.error(f"Entity extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Entity extraction failed: {str(e)}"
        )


@router.post("/extract-entities/bulk")
async def bulk_extract_entities(
    db: AsyncSession = Depends(get_db),
    current_user: LocalUser = Depends(get_local_user),
    hours: int = Query(720, ge=1, le=8760, description="Time window in hours (default 30 days, max 1 year)"),
    limit: int = Query(500, ge=1, le=2000, description="Max items to process"),
):
    """
    Bulk entity extraction for backlog processing.

    - Extracts entities using GLiNER only (no WikiData linking)
    - Much faster than standard extraction
    - WikiData enrichment runs separately via /enrich-entities

    Use this for processing large backlogs efficiently.

    Args:
        hours: Time window in hours (default 720 = 30 days)
        limit: Maximum items to process (up to 2000)

    Returns:
        Extraction statistics
    """
    manager = get_extraction_manager()

    # Check if extraction already in progress
    if await manager.is_extraction_active():
        status = await manager.get_status()
        return JSONResponse(
            status_code=202,
            content={
                "status": "queued",
                "message": "Extraction already in progress. Your request is queued.",
                "active_task": status["active_task"],
                "queue_position": status["queue_size"] + 1,
            }
        )

    task = await manager.acquire_slot()
    try:
        logger.info(f"Starting BULK entity extraction: hours={hours}, limit={limit} (no WikiData)")

        # Create extractor WITHOUT WikiData linker for speed
        extractor = AutoEntityExtractor(
            db_session=db,
            user_id=current_user.user_id,
            wikidata_linker=None  # No WikiData for bulk
        )

        async def update_progress(processed: int, total: int):
            await manager.update_progress(task, processed, total)

        result = await extractor.batch_extract_recent(
            hours=hours,
            limit=limit,
            auto_track=True,
            auto_track_threshold=0.7,
            progress_callback=update_progress
        )

        await manager.release_slot(task, success=True)

        return {
            "status": "completed",
            "request_id": str(task.request_id),
            "stats": {
                "items_processed": result.items_processed,
                "total_entities_extracted": result.total_entities_extracted,
                "unique_entities": result.unique_entities,
                "new_entities_created": result.new_entities_created,
                "mentions_created": result.mentions_created,
                "processing_time_seconds": round(result.processing_time_seconds, 2),
            },
            "note": "Entities created without WikiData. Run /enrich-entities to add WikiData metadata.",
            "errors": result.errors[:5] if result.errors else [],
        }

    except Exception as e:
        await manager.release_slot(task, success=False, error=str(e))
        logger.error(f"Bulk entity extraction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Bulk entity extraction failed: {str(e)}"
        )


@router.post("/enrich-entities")
async def enrich_entities_with_wikidata(
    db: AsyncSession = Depends(get_db),
    current_user: LocalUser = Depends(get_local_user),
    wikidata_linker: WikiDataLinker = Depends(get_wikidata_linker),
    limit: int = Query(100, ge=1, le=500, description="Max entities to enrich per call"),
    concurrent: int = Query(5, ge=1, le=10, description="Parallel WikiData lookups"),
):
    """
    Enrich entities that lack WikiData metadata.

    - Processes entities missing wikidata_id in metadata
    - Uses parallel WikiData lookups with rate limiting
    - Run multiple times to process backlog
    - Redis cache reduces repeat lookups

    Args:
        limit: Maximum entities to enrich per call (1-500)
        concurrent: Number of parallel WikiData lookups (1-10)

    Returns:
        Enrichment statistics
    """
    try:
        # Find entities without WikiData
        # Use raw SQL for JSON key check since entity_metadata is JSON (not JSONB)
        query = (
            select(TrackedEntity)
            .where(TrackedEntity.user_id == str(current_user.user_id))
            .where(
                or_(
                    TrackedEntity.entity_metadata.is_(None),
                    text("entity_metadata->>'wikidata_id' IS NULL"),
                    text("entity_metadata->>'wikidata_id' = ''"),
                )
            )
            .limit(limit)
        )
        result = await db.execute(query)
        entities = list(result.scalars().all())

        if not entities:
            # Count total for info
            total_query = select(func.count(TrackedEntity.entity_id)).where(
                TrackedEntity.user_id == str(current_user.user_id)
            )
            total_result = await db.execute(total_query)
            total_count = total_result.scalar() or 0

            return {
                "status": "completed",
                "enriched": 0,
                "message": "All entities already have WikiData metadata",
                "total_entities": total_count,
            }

        logger.info(f"Enriching {len(entities)} entities with WikiData (concurrent={concurrent})")

        # Parallel enrichment with semaphore
        semaphore = asyncio.Semaphore(concurrent)
        enriched = 0
        errors = []

        async def enrich_one(entity: TrackedEntity):
            nonlocal enriched
            async with semaphore:
                try:
                    linked = await wikidata_linker.link_entity(
                        entity.name, entity.entity_type
                    )
                    if linked:
                        # Update entity metadata
                        new_metadata = dict(entity.entity_metadata) if entity.entity_metadata else {}
                        new_metadata.update({
                            "wikidata_id": linked.wikidata_id,
                            "wikidata_description": linked.description,
                            "wikipedia_url": linked.wikipedia_url,
                            "canonical_name": linked.label,
                            "aliases": linked.aliases,
                        })
                        entity.entity_metadata = new_metadata
                        enriched += 1
                except Exception as e:
                    errors.append({"entity": entity.name, "error": str(e)})

        await asyncio.gather(*[enrich_one(e) for e in entities])
        await db.commit()

        # Count remaining unenriched
        remaining_query = (
            select(func.count(TrackedEntity.entity_id))
            .where(TrackedEntity.user_id == str(current_user.user_id))
            .where(
                or_(
                    TrackedEntity.entity_metadata.is_(None),
                    text("entity_metadata->>'wikidata_id' IS NULL"),
                    text("entity_metadata->>'wikidata_id' = ''"),
                )
            )
        )
        remaining_result = await db.execute(remaining_query)
        remaining = remaining_result.scalar() or 0

        return {
            "status": "completed",
            "enriched": enriched,
            "processed": len(entities),
            "errors": len(errors),
            "remaining": remaining,
            "error_details": errors[:5] if errors else [],
        }

    except Exception as e:
        logger.error(f"Entity enrichment failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Entity enrichment failed: {str(e)}"
        )


@router.post("/extract-entities/{item_id}")
async def extract_entities_from_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: LocalUser = Depends(get_local_user),
    auto_track: bool = Query(True, description="Auto-track high-confidence entities"),
    confidence_threshold: float = Query(0.7, ge=0.3, le=1.0),
):
    """
    Extract entities from a specific news item.

    Args:
        item_id: NewsItem UUID
        auto_track: Whether to auto-track high-confidence entities
        confidence_threshold: Minimum confidence for auto-tracking

    Returns:
        Extraction result with found entities
    """
    try:
        import uuid
        item_uuid = uuid.UUID(item_id)

        extractor = AutoEntityExtractor(
            db_session=db,
            user_id=current_user.user_id
        )

        result = await extractor.extract_from_news_item(
            news_item_id=item_uuid,
            auto_track=auto_track,
            auto_track_threshold=confidence_threshold
        )

        return {
            "status": "completed",
            "item_id": item_id,
            "entities_found": len(result.extracted_entities),
            "new_entities_created": result.new_entities_created,
            "mentions_created": result.mentions_created,
            "entities": [
                {
                    "text": e.text,
                    "type": e.entity_type,
                    "confidence": round(e.confidence, 3),
                    "normalized": e.normalized,
                }
                for e in result.extracted_entities
            ],
            "wikidata_links": {
                name: {
                    "qid": link.wikidata_id,
                    "label": link.label,
                    "description": link.description,
                } if link else None
                for name, link in result.linked_entities.items()
            },
            "processing_time_ms": round(result.processing_time_ms, 2),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid item ID: {str(e)}")
    except Exception as e:
        logger.error(f"Entity extraction failed for {item_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Entity extraction failed: {str(e)}"
        )
