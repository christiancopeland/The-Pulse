"""
Briefing Archive for The Pulse.

SYNTH-005: Briefing Archive

Stores and retrieves past briefings for historical reference
and continuity in intelligence analysis.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import logging
import os
import uuid

from sqlalchemy import Column, String, DateTime, Text, Integer, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base
from app.services.synthesis.briefing_generator import Briefing, BriefingSection

logger = logging.getLogger(__name__)


class BriefingRecord(Base):
    """Database model for archived briefings."""
    __tablename__ = "briefings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    generated_at = Column(DateTime(timezone=True), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    title = Column(String(500), nullable=False)
    executive_summary = Column(Text, nullable=False)
    sections = Column(JSONB, default=list)
    entity_highlights = Column(JSONB, default=list)
    audio_path = Column(String(500), nullable=True)
    briefing_metadata = Column(JSONB, default=dict)  # Renamed from 'metadata' (reserved)
    user_id = Column(String(36), nullable=True)  # Optional user association

    def to_briefing(self) -> Briefing:
        """Convert database record to Briefing object."""
        sections = [
            BriefingSection(**s) for s in (self.sections or [])
        ]

        return Briefing(
            id=self.id,
            generated_at=self.generated_at,
            period_start=self.period_start,
            period_end=self.period_end,
            title=self.title,
            executive_summary=self.executive_summary,
            sections=sections,
            entity_highlights=self.entity_highlights or [],
            audio_path=self.audio_path,
            metadata=self.briefing_metadata or {},
        )


class BriefingArchive:
    """
    Manages storage and retrieval of briefings.

    Provides persistence for generated briefings with
    search and filtering capabilities.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        file_storage_dir: Optional[str] = None
    ):
        """
        Initialize briefing archive.

        Args:
            db_session: Async database session
            file_storage_dir: Directory for file-based storage (fallback)
        """
        self.db = db_session
        self.file_storage_dir = Path(
            file_storage_dir or os.getenv("BRIEFING_STORAGE_DIR", "data/briefings")
        )
        self.file_storage_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(f"{__name__}.BriefingArchive")

    async def save(self, briefing: Briefing, user_id: Optional[str] = None) -> str:
        """
        Save a briefing to the archive.

        Args:
            briefing: Briefing to save
            user_id: Optional user ID to associate

        Returns:
            Briefing ID
        """
        try:
            # Convert sections to dicts
            sections_data = [
                {
                    "title": s.title,
                    "topic": s.topic,
                    "summary": s.summary,
                    "key_developments": s.key_developments,
                    "entities_mentioned": s.entities_mentioned,
                    "sources_used": s.sources_used,
                }
                for s in briefing.sections
            ]

            record = BriefingRecord(
                id=briefing.id,
                generated_at=briefing.generated_at,
                period_start=briefing.period_start,
                period_end=briefing.period_end,
                title=briefing.title,
                executive_summary=briefing.executive_summary,
                sections=sections_data,
                entity_highlights=briefing.entity_highlights,
                audio_path=briefing.audio_path,
                briefing_metadata=briefing.metadata,
                user_id=user_id,
            )

            self.db.add(record)
            await self.db.commit()

            self._logger.info(f"Saved briefing {briefing.id} to archive")

            # Also save as file for backup
            await self._save_to_file(briefing)

            return briefing.id

        except Exception as e:
            self._logger.error(f"Failed to save briefing: {e}")
            await self.db.rollback()

            # Fallback to file-only storage
            await self._save_to_file(briefing)
            return briefing.id

    async def _save_to_file(self, briefing: Briefing) -> str:
        """Save briefing to file as JSON."""
        file_path = self.file_storage_dir / f"{briefing.id}.json"

        try:
            with open(file_path, 'w') as f:
                json.dump(briefing.to_dict(), f, indent=2, default=str)

            # Also save markdown version
            md_path = self.file_storage_dir / f"{briefing.id}.md"
            with open(md_path, 'w') as f:
                f.write(briefing.to_markdown())

            return str(file_path)

        except Exception as e:
            self._logger.error(f"Failed to save briefing to file: {e}")
            raise

    async def get(self, briefing_id: str) -> Optional[Briefing]:
        """
        Retrieve a briefing by ID.

        Args:
            briefing_id: Briefing ID

        Returns:
            Briefing or None if not found
        """
        try:
            query = select(BriefingRecord).where(BriefingRecord.id == briefing_id)
            result = await self.db.execute(query)
            record = result.scalar_one_or_none()

            if record:
                return record.to_briefing()

        except Exception as e:
            self._logger.warning(f"Database lookup failed: {e}")

        # Fallback to file storage
        return await self._get_from_file(briefing_id)

    async def _get_from_file(self, briefing_id: str) -> Optional[Briefing]:
        """Load briefing from file."""
        file_path = self.file_storage_dir / f"{briefing_id}.json"

        if not file_path.exists():
            return None

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)

            sections = [BriefingSection(**s) for s in data.get("sections", [])]

            return Briefing(
                id=data["id"],
                generated_at=datetime.fromisoformat(data["generated_at"]),
                period_start=datetime.fromisoformat(data["period_start"]),
                period_end=datetime.fromisoformat(data["period_end"]),
                title=data["title"],
                executive_summary=data["executive_summary"],
                sections=sections,
                entity_highlights=data.get("entity_highlights", []),
                audio_path=data.get("audio_path"),
                metadata=data.get("metadata", {}),
            )

        except Exception as e:
            self._logger.error(f"Failed to load briefing from file: {e}")
            return None

    async def list(
        self,
        limit: int = 10,
        offset: int = 0,
        user_id: Optional[str] = None,
        before: Optional[datetime] = None,
        after: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        List archived briefings.

        Args:
            limit: Maximum number to return
            offset: Offset for pagination
            user_id: Filter by user ID
            before: Filter by generated before date
            after: Filter by generated after date

        Returns:
            List of briefing summaries
        """
        try:
            # Build query
            conditions = []

            if user_id:
                conditions.append(BriefingRecord.user_id == user_id)
            if before:
                conditions.append(BriefingRecord.generated_at < before)
            if after:
                conditions.append(BriefingRecord.generated_at > after)

            query = (
                select(BriefingRecord)
                .order_by(desc(BriefingRecord.generated_at))
                .limit(limit)
                .offset(offset)
            )

            if conditions:
                query = query.where(and_(*conditions))

            result = await self.db.execute(query)
            records = result.scalars().all()

            return [
                {
                    "id": r.id,
                    "title": r.title,
                    "generated_at": r.generated_at.isoformat(),
                    "period_start": r.period_start.isoformat(),
                    "period_end": r.period_end.isoformat(),
                    "section_count": len(r.sections or []),
                    "has_audio": bool(r.audio_path),
                }
                for r in records
            ]

        except Exception as e:
            self._logger.warning(f"Database list failed: {e}")
            return await self._list_from_files(limit)

    async def _list_from_files(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List briefings from file storage."""
        briefings = []

        for file_path in sorted(
            self.file_storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]:
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                briefings.append({
                    "id": data["id"],
                    "title": data["title"],
                    "generated_at": data["generated_at"],
                    "period_start": data["period_start"],
                    "period_end": data["period_end"],
                    "section_count": len(data.get("sections", [])),
                    "has_audio": bool(data.get("audio_path")),
                })

            except Exception as e:
                self._logger.warning(f"Failed to read {file_path}: {e}")

        return briefings

    async def delete(self, briefing_id: str) -> bool:
        """
        Delete a briefing from the archive.

        Args:
            briefing_id: Briefing ID

        Returns:
            True if deleted successfully
        """
        deleted = False

        # Delete from database
        try:
            query = select(BriefingRecord).where(BriefingRecord.id == briefing_id)
            result = await self.db.execute(query)
            record = result.scalar_one_or_none()

            if record:
                await self.db.delete(record)
                await self.db.commit()
                deleted = True

        except Exception as e:
            self._logger.warning(f"Database delete failed: {e}")

        # Delete from file storage
        for ext in ['json', 'md']:
            file_path = self.file_storage_dir / f"{briefing_id}.{ext}"
            if file_path.exists():
                try:
                    file_path.unlink()
                    deleted = True
                except Exception as e:
                    self._logger.error(f"Failed to delete {file_path}: {e}")

        return deleted

    async def search(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search briefings by title or content.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching briefing summaries
        """
        query_lower = query.lower()
        results = []

        # Search in files (simple text search)
        for file_path in self.file_storage_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)

                # Check title and summary
                if (
                    query_lower in data.get("title", "").lower() or
                    query_lower in data.get("executive_summary", "").lower()
                ):
                    results.append({
                        "id": data["id"],
                        "title": data["title"],
                        "generated_at": data["generated_at"],
                        "match_type": "title" if query_lower in data.get("title", "").lower() else "content",
                    })

                if len(results) >= limit:
                    break

            except Exception:
                continue

        return results

    async def get_latest(self, user_id: Optional[str] = None) -> Optional[Briefing]:
        """
        Get the most recent briefing.

        Args:
            user_id: Optional user filter

        Returns:
            Most recent Briefing or None
        """
        try:
            query = (
                select(BriefingRecord)
                .order_by(desc(BriefingRecord.generated_at))
                .limit(1)
            )

            if user_id:
                query = query.where(BriefingRecord.user_id == user_id)

            result = await self.db.execute(query)
            record = result.scalar_one_or_none()

            if record:
                return record.to_briefing()

        except Exception as e:
            self._logger.warning(f"Database latest lookup failed: {e}")

        # Fallback to files
        files = sorted(
            self.file_storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if files:
            return await self._get_from_file(files[0].stem)

        return None

    async def get_stats(self) -> Dict[str, Any]:
        """Get archive statistics."""
        try:
            # Count from database
            from sqlalchemy import func
            count_query = select(func.count(BriefingRecord.id))
            result = await self.db.execute(count_query)
            db_count = result.scalar()

            # Get date range
            range_query = select(
                func.min(BriefingRecord.generated_at),
                func.max(BriefingRecord.generated_at)
            )
            range_result = await self.db.execute(range_query)
            min_date, max_date = range_result.first()

            return {
                "total_briefings": db_count,
                "earliest": min_date.isoformat() if min_date else None,
                "latest": max_date.isoformat() if max_date else None,
                "storage_dir": str(self.file_storage_dir),
            }

        except Exception as e:
            # Fallback to file count
            file_count = len(list(self.file_storage_dir.glob("*.json")))
            return {
                "total_briefings": file_count,
                "storage_dir": str(self.file_storage_dir),
                "source": "file_fallback",
            }
