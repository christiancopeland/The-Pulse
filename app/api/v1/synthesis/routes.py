"""
Synthesis API routes for The Pulse.

Phase 4 & 5: Synthesis Engine API

Provides endpoints for:
- POST /generate - Generate a new briefing
- GET /briefings - List archived briefings
- GET /briefings/{id} - Get specific briefing
- GET /briefings/{id}/audio - Get briefing audio
- GET /briefings/latest - Get most recent briefing
- DELETE /briefings/{id} - Delete a briefing
- POST /briefings/{id}/audio - Generate audio for existing briefing
- GET /trends - Get current trend indicators (Phase 5)
- GET /trends/categories - Get category breakdown (Phase 5)
"""
import logging
import time
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user_optional
from app.models.user import User
from typing import Optional as OptionalType
from app.services.synthesis.briefing_generator import BriefingGenerator, Briefing
from app.services.synthesis.tiered_briefing import (
    TieredBriefingGenerator,
    TieredBriefing,
    IntelligenceTier,
)
from app.services.synthesis.pattern_detector import PatternDetector
from app.services.synthesis.briefing_archive import BriefingArchive
from app.services.synthesis.audio_generator import AudioGenerator
from app.services.synthesis.trend_indicators import TrendIndicatorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/synthesis", tags=["synthesis"])


# Pydantic models for request/response
class BriefingGenerateRequest(BaseModel):
    """Request body for briefing generation."""
    period_hours: int = 24
    include_audio: bool = False
    custom_title: Optional[str] = None
    topic_focus: Optional[str] = None


class TieredBriefingRequest(BaseModel):
    """Request body for tiered briefing generation."""
    period_hours: int = 24
    include_audio: bool = False
    include_so_what: bool = True
    tracked_entities: Optional[List[str]] = None


class BriefingResponse(BaseModel):
    """Response for briefing data."""
    id: str
    title: str
    generated_at: str
    period_start: str
    period_end: str
    executive_summary: str
    sections: List[dict]
    entity_highlights: List[dict]
    has_audio: bool
    metadata: dict

    @classmethod
    def from_briefing(cls, briefing: Briefing) -> "BriefingResponse":
        return cls(
            id=briefing.id,
            title=briefing.title,
            generated_at=briefing.generated_at.isoformat(),
            period_start=briefing.period_start.isoformat(),
            period_end=briefing.period_end.isoformat(),
            executive_summary=briefing.executive_summary,
            sections=[
                {
                    "title": s.title,
                    "topic": s.topic,
                    "summary": s.summary,
                    "key_developments": s.key_developments,
                    "entities_mentioned": s.entities_mentioned,
                    "sources_used": s.sources_used,
                }
                for s in briefing.sections
            ],
            entity_highlights=briefing.entity_highlights,
            has_audio=briefing.audio_path is not None,
            metadata=briefing.metadata,
        )


class BriefingListItem(BaseModel):
    """Summary item for briefing list."""
    id: str
    title: str
    generated_at: str
    period_start: str
    period_end: str
    section_count: int
    has_audio: bool


class BriefingListResponse(BaseModel):
    """Response for briefing list."""
    briefings: List[BriefingListItem]
    total: int


@router.post("/generate", response_model=BriefingResponse)
async def generate_briefing(
    request: BriefingGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Generate a new intelligence briefing.

    Creates a synthesized briefing from collected news items
    for the specified time period.
    """
    start_time = time.time()
    user_id = str(current_user.user_id) if current_user else None

    logger.info(
        f"[SYNTHESIS] Generate briefing request: period_hours={request.period_hours}, "
        f"topic_focus={request.topic_focus}, include_audio={request.include_audio}, "
        f"user_id={user_id or 'anonymous'}"
    )

    try:
        generator = BriefingGenerator(db_session=db)

        if request.topic_focus:
            logger.debug(f"[SYNTHESIS] Generating focused briefing on topic: {request.topic_focus}")
            briefing = await generator.generate_focused_briefing(
                topic=request.topic_focus,
                period_hours=request.period_hours,
                user_id=user_id,
            )
        else:
            logger.debug(f"[SYNTHESIS] Generating full briefing for last {request.period_hours} hours")
            briefing = await generator.generate(
                period_hours=request.period_hours,
                user_id=user_id,
                include_audio=request.include_audio,
                custom_title=request.custom_title,
            )

        logger.info(
            f"[SYNTHESIS] Briefing generated: id={briefing.id}, "
            f"sections={len(briefing.sections)}, entities={len(briefing.entity_highlights)}"
        )

        # Save to archive
        archive = BriefingArchive(db_session=db)
        await archive.save(briefing, user_id=user_id or "local")
        logger.debug(f"[SYNTHESIS] Briefing {briefing.id} saved to archive")

        elapsed = time.time() - start_time
        logger.info(f"[SYNTHESIS] Generate complete: id={briefing.id}, elapsed={elapsed:.2f}s")

        return BriefingResponse.from_briefing(briefing)

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[SYNTHESIS] Briefing generation failed after {elapsed:.2f}s: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Briefing generation failed: {e}")


@router.post("/generate/tiered")
async def generate_tiered_briefing(
    request: TieredBriefingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Generate a tiered intelligence briefing.

    Returns the full tiered structure with:
    - Tier 1 (Actionable): Geopolitical/Military
    - Tier 2 (Situational): Local Government
    - Tier 3 (Background): Tech/AI
    - Tier 4 (Monitor): Financial/Business

    Each tier includes "So What?" analysis and pattern alerts.
    """
    start_time = time.time()
    user_id = str(current_user.user_id) if current_user else None

    logger.info(
        f"[SYNTHESIS] Generate tiered briefing: period_hours={request.period_hours}, "
        f"entities={len(request.tracked_entities or [])}, user_id={user_id or 'anonymous'}"
    )

    try:
        pattern_detector = PatternDetector(db_session=db)
        generator = TieredBriefingGenerator(
            db_session=db,
            pattern_detector=pattern_detector,
        )

        briefing = await generator.generate(
            period_hours=request.period_hours,
            user_id=user_id,
            tracked_entities=request.tracked_entities,
            include_so_what=request.include_so_what,
            include_audio=request.include_audio,
        )

        logger.info(
            f"[SYNTHESIS] Tiered briefing generated: id={briefing.id}, "
            f"T1={briefing.items_by_tier.get(1, 0)}, T2={briefing.items_by_tier.get(2, 0)}, "
            f"T3={briefing.items_by_tier.get(3, 0)}, T4={briefing.items_by_tier.get(4, 0)}, "
            f"alerts={len(briefing.pattern_alerts)}"
        )

        elapsed = time.time() - start_time
        logger.info(f"[SYNTHESIS] Tiered briefing complete: elapsed={elapsed:.2f}s")

        return briefing.to_dict()

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[SYNTHESIS] Tiered briefing failed after {elapsed:.2f}s: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Tiered briefing generation failed: {e}")


@router.get("/briefings", response_model=BriefingListResponse)
async def list_briefings(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    before: Optional[datetime] = None,
    after: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    List archived briefings.

    Returns a paginated list of briefing summaries.
    """
    user_id = str(current_user.user_id) if current_user else None
    logger.debug(
        f"[SYNTHESIS] List briefings: limit={limit}, offset={offset}, "
        f"before={before}, after={after}, user_id={user_id or 'all'}"
    )

    archive = BriefingArchive(db_session=db)

    briefings = await archive.list(
        limit=limit,
        offset=offset,
        user_id=user_id,
        before=before,
        after=after,
    )

    logger.info(f"[SYNTHESIS] Listed {len(briefings)} briefings")

    return BriefingListResponse(
        briefings=[
            BriefingListItem(
                id=b["id"],
                title=b["title"],
                generated_at=b["generated_at"],
                period_start=b["period_start"],
                period_end=b["period_end"],
                section_count=b["section_count"],
                has_audio=b["has_audio"],
            )
            for b in briefings
        ],
        total=len(briefings),
    )


@router.get("/briefings/latest", response_model=BriefingResponse)
async def get_latest_briefing(
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get the most recent briefing.
    """
    user_id = str(current_user.user_id) if current_user else None
    logger.debug(f"[SYNTHESIS] Get latest briefing for user_id={user_id or 'all'}")

    archive = BriefingArchive(db_session=db)
    briefing = await archive.get_latest(user_id=user_id)

    if not briefing:
        logger.warning(f"[SYNTHESIS] No briefings found for user_id={user_id or 'all'}")
        raise HTTPException(status_code=404, detail="No briefings found")

    logger.info(f"[SYNTHESIS] Returning latest briefing: id={briefing.id}")
    return BriefingResponse.from_briefing(briefing)


@router.get("/briefings/{briefing_id}", response_model=BriefingResponse)
async def get_briefing(
    briefing_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get a specific briefing by ID.
    """
    logger.debug(f"[SYNTHESIS] Get briefing: id={briefing_id}")

    archive = BriefingArchive(db_session=db)
    briefing = await archive.get(briefing_id)

    if not briefing:
        logger.warning(f"[SYNTHESIS] Briefing not found: id={briefing_id}")
        raise HTTPException(status_code=404, detail="Briefing not found")

    logger.debug(f"[SYNTHESIS] Returning briefing: id={briefing_id}, title={briefing.title}")
    return BriefingResponse.from_briefing(briefing)


@router.get("/briefings/{briefing_id}/markdown")
async def get_briefing_markdown(
    briefing_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get briefing content as markdown.
    """
    logger.debug(f"[SYNTHESIS] Get briefing markdown: id={briefing_id}")

    archive = BriefingArchive(db_session=db)
    briefing = await archive.get(briefing_id)

    if not briefing:
        logger.warning(f"[SYNTHESIS] Briefing not found for markdown export: id={briefing_id}")
        raise HTTPException(status_code=404, detail="Briefing not found")

    logger.info(f"[SYNTHESIS] Exporting briefing as markdown: id={briefing_id}")
    return Response(
        content=briefing.to_markdown(),
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{briefing_id}.md"'
        }
    )


@router.get("/briefings/{briefing_id}/audio")
async def get_briefing_audio(
    briefing_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get audio file for a briefing.
    """
    logger.debug(f"[SYNTHESIS] Get briefing audio: id={briefing_id}")

    archive = BriefingArchive(db_session=db)
    briefing = await archive.get(briefing_id)

    if not briefing:
        logger.warning(f"[SYNTHESIS] Briefing not found for audio: id={briefing_id}")
        raise HTTPException(status_code=404, detail="Briefing not found")

    if not briefing.audio_path:
        logger.warning(f"[SYNTHESIS] No audio available for briefing: id={briefing_id}")
        raise HTTPException(status_code=404, detail="No audio available for this briefing")

    audio_path = Path(briefing.audio_path)
    if not audio_path.exists():
        logger.error(f"[SYNTHESIS] Audio file missing from disk: path={audio_path}")
        raise HTTPException(status_code=404, detail="Audio file not found")

    logger.info(f"[SYNTHESIS] Serving audio file: id={briefing_id}, path={audio_path}")
    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename=f"{briefing_id}.wav"
    )


@router.post("/briefings/{briefing_id}/audio")
async def generate_briefing_audio(
    briefing_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Generate audio for an existing briefing.
    """
    start_time = time.time()
    logger.info(f"[SYNTHESIS] Generate audio request: briefing_id={briefing_id}")

    archive = BriefingArchive(db_session=db)
    briefing = await archive.get(briefing_id)

    if not briefing:
        logger.warning(f"[SYNTHESIS] Briefing not found for audio generation: id={briefing_id}")
        raise HTTPException(status_code=404, detail="Briefing not found")

    if briefing.audio_path:
        logger.info(f"[SYNTHESIS] Audio already exists for briefing: id={briefing_id}")
        return {"message": "Audio already exists", "audio_path": briefing.audio_path}

    # Generate audio
    logger.debug(f"[SYNTHESIS] Starting TTS generation for briefing: id={briefing_id}")
    audio_gen = AudioGenerator()
    audio_path = await audio_gen.generate(
        briefing.to_markdown(),
        briefing.id
    )

    if not audio_path:
        elapsed = time.time() - start_time
        logger.error(f"[SYNTHESIS] Audio generation failed after {elapsed:.2f}s: id={briefing_id}")
        raise HTTPException(status_code=500, detail="Audio generation failed")

    # Update briefing with audio path
    briefing.audio_path = audio_path
    await archive.save(briefing, user_id=str(current_user.user_id) if current_user else "local")

    elapsed = time.time() - start_time
    logger.info(f"[SYNTHESIS] Audio generated: id={briefing_id}, path={audio_path}, elapsed={elapsed:.2f}s")

    return {"message": "Audio generated", "audio_path": audio_path}


@router.delete("/briefings/{briefing_id}")
async def delete_briefing(
    briefing_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Delete a briefing from the archive.
    """
    logger.info(f"[SYNTHESIS] Delete briefing request: id={briefing_id}")

    archive = BriefingArchive(db_session=db)

    # Check briefing exists
    briefing = await archive.get(briefing_id)
    if not briefing:
        logger.warning(f"[SYNTHESIS] Briefing not found for deletion: id={briefing_id}")
        raise HTTPException(status_code=404, detail="Briefing not found")

    # Delete audio if exists
    if briefing.audio_path:
        logger.debug(f"[SYNTHESIS] Deleting associated audio: id={briefing_id}")
        audio_gen = AudioGenerator()
        audio_gen.delete_audio(briefing_id)

    # Delete briefing
    deleted = await archive.delete(briefing_id)

    if not deleted:
        logger.error(f"[SYNTHESIS] Failed to delete briefing: id={briefing_id}")
        raise HTTPException(status_code=500, detail="Failed to delete briefing")

    logger.info(f"[SYNTHESIS] Briefing deleted: id={briefing_id}")
    return {"message": "Briefing deleted", "id": briefing_id}


@router.get("/stats")
async def get_synthesis_stats(
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get synthesis system statistics.
    """
    logger.debug("[SYNTHESIS] Getting synthesis stats")

    archive = BriefingArchive(db_session=db)
    stats = await archive.get_stats()

    audio_gen = AudioGenerator()
    audio_files = audio_gen.list_audio_files()

    logger.debug(f"[SYNTHESIS] Stats: archive={stats}, audio_files={len(audio_files)}")

    return {
        "archive": stats,
        "audio": {
            "total_files": len(audio_files),
            "total_size_bytes": sum(f["size"] for f in audio_files),
        },
    }


@router.get("/voices")
async def list_available_voices():
    """
    List available TTS voices.
    """
    logger.debug("[SYNTHESIS] Listing available voices")
    audio_gen = AudioGenerator()
    voices = audio_gen.get_available_voices()

    return {
        "voices": voices,
        "default": AudioGenerator.DEFAULT_VOICE,
    }


# =============================================================================
# Phase 5: Trend Indicator Endpoints
# =============================================================================


@router.get("/trends")
async def get_trend_indicators(
    period_days: int = Query(30, ge=1, le=90, description="Days for current period"),
    baseline_days: int = Query(180, ge=30, le=365, description="Days for baseline calculation"),
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get current trend indicators.

    Returns 6-month rolling trend analysis for:
    - Conflict Index: Armed conflict and security events
    - Market Volatility: Financial and business activity
    - Political Instability: Political turmoil and governance events
    - Tech Activity: Technology and AI developments
    - Entity Activity: Tracked entity mention frequency
    - Collection Health: Data collection system status

    Each indicator includes:
    - Current value and baseline comparison
    - Change percentage and direction (rising/falling/stable)
    - Alert level (normal/elevated/critical)
    - Sparkline data for visualization
    """
    start_time = time.time()
    user_id = str(current_user.user_id) if current_user else None

    logger.info(
        f"[SYNTHESIS] Get trends: period={period_days}d, baseline={baseline_days}d, "
        f"user_id={user_id or 'anonymous'}"
    )

    try:
        service = TrendIndicatorService(db_session=db)
        snapshot = await service.compute_all_indicators(
            user_id=user_id,
            period_days=period_days,
            baseline_days=baseline_days,
        )

        elapsed = time.time() - start_time
        logger.info(
            f"[SYNTHESIS] Trends computed: overall_status={snapshot.overall_status.value}, "
            f"indicators={len(snapshot.indicators)}, elapsed={elapsed:.2f}s"
        )

        return snapshot.to_dict()

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[SYNTHESIS] Trend computation failed after {elapsed:.2f}s: {e}",
            exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Trend computation failed: {e}")


@router.get("/trends/categories")
async def get_category_breakdown(
    period_days: int = Query(30, ge=1, le=90, description="Days for analysis period"),
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get breakdown of collected items by source type/category.

    Returns counts of items by source type for the specified period.
    """
    logger.debug(f"[SYNTHESIS] Get category breakdown: period={period_days}d")

    try:
        service = TrendIndicatorService(db_session=db)
        breakdown = await service.get_category_breakdown(period_days=period_days)

        total = sum(breakdown.values())
        logger.info(f"[SYNTHESIS] Category breakdown: {len(breakdown)} categories, {total} total items")

        return {
            "period_days": period_days,
            "total_items": total,
            "breakdown": breakdown,
        }

    except Exception as e:
        logger.error(f"[SYNTHESIS] Category breakdown failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Category breakdown failed: {e}")


@router.get("/trends/summary")
async def get_trend_summary(
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[User] = Depends(get_current_user_optional),
):
    """
    Get a concise summary of current trend status.

    Returns overall status and key alerts without full sparkline data.
    Useful for dashboard status indicators.
    """
    user_id = str(current_user.user_id) if current_user else None
    logger.debug(f"[SYNTHESIS] Get trend summary: user_id={user_id or 'anonymous'}")

    try:
        service = TrendIndicatorService(db_session=db)
        snapshot = await service.compute_all_indicators(
            user_id=user_id,
            period_days=30,
            baseline_days=180,
        )

        # Build concise summary
        alerts = []
        for name, indicator in snapshot.indicators.items():
            if indicator.alert_level.value != "normal":
                alerts.append({
                    "indicator": name,
                    "level": indicator.alert_level.value,
                    "change": round(indicator.change_percent, 1),
                    "direction": indicator.direction.value,
                })

        return {
            "overall_status": snapshot.overall_status.value,
            "summary": snapshot.summary,
            "generated_at": snapshot.generated_at.isoformat(),
            "alerts": alerts,
            "indicator_count": len(snapshot.indicators),
        }

    except Exception as e:
        logger.error(f"[SYNTHESIS] Trend summary failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Trend summary failed: {e}")
