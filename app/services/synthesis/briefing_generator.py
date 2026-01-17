"""
Briefing Generator for The Pulse.

SYNTH-002: Daily Briefing Generator
SYNTH-003: Entity-Aware Prompts

This module provides backward-compatible interfaces to the new
TieredBriefingGenerator. The original flat briefing structure is
maintained for compatibility with BriefingArchive and existing API routes.

For new code, use TieredBriefingGenerator directly from tiered_briefing.py.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.synthesis.context_builder import ContextBuilder, SynthesisContext
from app.services.synthesis.tiered_briefing import (
    TieredBriefingGenerator,
    TieredBriefing,
    TieredBriefingSection,
    TieredBriefingItem,
    IntelligenceTier,
    PatternAlert,
)
from app.services.synthesis.pattern_detector import PatternDetector
from app.models.news_item import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class BriefingSection:
    """
    A section within a briefing (legacy format).

    This maintains backward compatibility with BriefingArchive.
    For new code, use TieredBriefingSection instead.
    """
    title: str
    topic: str
    summary: str
    key_developments: List[str] = field(default_factory=list)
    entities_mentioned: List[str] = field(default_factory=list)
    sources_used: List[str] = field(default_factory=list)


@dataclass
class Briefing:
    """
    Complete intelligence briefing (legacy format).

    This maintains backward compatibility with BriefingArchive.
    For new code, use TieredBriefing instead.
    """
    id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    title: str
    executive_summary: str
    sections: List[BriefingSection] = field(default_factory=list)
    entity_highlights: List[Dict[str, Any]] = field(default_factory=list)
    audio_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert briefing to dictionary."""
        return {
            "id": self.id,
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "title": self.title,
            "executive_summary": self.executive_summary,
            "sections": [asdict(s) for s in self.sections],
            "entity_highlights": self.entity_highlights,
            "audio_path": self.audio_path,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """Convert briefing to markdown format."""
        lines = []

        # Header
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(
            f"**Period:** {self.period_start.strftime('%Y-%m-%d %H:%M')} - "
            f"{self.period_end.strftime('%Y-%m-%d %H:%M')}"
        )
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(self.executive_summary)
        lines.append("")

        # Pattern Alerts (from metadata if present)
        pattern_alerts = self.metadata.get("pattern_alerts", [])
        if pattern_alerts:
            lines.append("## Pattern Alerts")
            lines.append("")
            for alert in pattern_alerts:
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(
                    alert.get("severity", "low"), "⚪"
                )
                lines.append(f"{severity_icon} **{alert.get('alert_type', 'Alert').upper()}**: {alert.get('description', '')}")
            lines.append("")

        # Sections
        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.summary)
            lines.append("")

            if section.key_developments:
                lines.append("**Key Developments:**")
                for dev in section.key_developments:
                    lines.append(f"- {dev}")
                lines.append("")

            if section.entities_mentioned:
                lines.append(f"**Entities:** {', '.join(section.entities_mentioned)}")
                lines.append("")

            if section.sources_used:
                lines.append(f"**Sources:** {', '.join(section.sources_used)}")
                lines.append("")

        # Entity Highlights
        if self.entity_highlights:
            lines.append("## Entity Highlights")
            lines.append("")
            for entity in self.entity_highlights:
                trend = entity.get("trend", "stable")
                trend_icon = {"rising": "📈", "falling": "📉", "stable": "➡️"}.get(trend, "")
                lines.append(
                    f"- **{entity['name']}** ({entity.get('entity_type', 'Unknown')}): "
                    f"{entity.get('mention_count', 0)} mentions {trend_icon}"
                )
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Items analyzed: {self.metadata.get('items_analyzed', self.metadata.get('total_items_analyzed', 0))}*")
        sources = self.metadata.get("sources", [])
        if sources:
            lines.append(f"*Sources: {', '.join(sources)}*")

        return "\n".join(lines)


def convert_tiered_to_legacy(tiered: TieredBriefing) -> Briefing:
    """
    Convert a TieredBriefing to legacy Briefing format.

    This allows the new tiered system to work with existing
    BriefingArchive and API routes.
    """
    sections = []

    for tiered_section in tiered.sections:
        # Convert tiered section to legacy format
        # Combine item titles as key developments
        key_developments = [item.title for item in tiered_section.items[:5]]

        # Collect entities from items
        entities = set()
        sources = set()
        for item in tiered_section.items:
            entities.update(item.entities_mentioned)
            sources.add(item.source_name)

        sections.append(BriefingSection(
            title=tiered_section.name,
            topic=tiered_section.tier.name.lower(),
            summary=tiered_section.synthesis,
            key_developments=key_developments,
            entities_mentioned=list(entities)[:10],
            sources_used=list(sources)[:5],
        ))

    # Serialize pattern alerts for metadata
    pattern_alerts_data = [
        {
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "entity": alert.entity,
            "description": alert.description,
        }
        for alert in tiered.pattern_alerts
    ]

    return Briefing(
        id=tiered.id,
        generated_at=tiered.generated_at,
        period_start=tiered.period_start,
        period_end=tiered.period_end,
        title=tiered.title,
        executive_summary=tiered.executive_summary,
        sections=sections,
        entity_highlights=tiered.entity_highlights,
        audio_path=tiered.audio_path,
        metadata={
            **tiered.metadata,
            "items_analyzed": tiered.total_items_analyzed,
            "items_by_tier": tiered.items_by_tier,
            "pattern_alerts": pattern_alerts_data,
            "tiered_format": True,  # Flag indicating this was converted
        },
    )


class BriefingGenerator:
    """
    Generates intelligence briefings from collected news items.

    This class wraps TieredBriefingGenerator and converts output
    to legacy Briefing format for backward compatibility.

    For new code using tiered output, use TieredBriefingGenerator directly.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        include_pattern_detection: bool = True,
    ):
        """
        Initialize briefing generator.

        Args:
            db_session: Async database session
            include_pattern_detection: Whether to run pattern detection
        """
        self.db = db_session
        pattern_detector = PatternDetector(db_session) if include_pattern_detection else None
        self._tiered_generator = TieredBriefingGenerator(
            db_session=db_session,
            pattern_detector=pattern_detector,
        )
        self._logger = logging.getLogger(f"{__name__}.BriefingGenerator")

    async def generate(
        self,
        period_hours: int = 24,
        user_id: Optional[str] = None,
        include_audio: bool = False,
        custom_title: Optional[str] = None,
    ) -> Briefing:
        """
        Generate a complete intelligence briefing.

        Args:
            period_hours: Hours to include in the briefing
            user_id: Optional user ID for entity context
            include_audio: Whether to generate audio version
            custom_title: Optional custom title for the briefing

        Returns:
            Complete Briefing object (legacy format)
        """
        self._logger.info(f"Generating briefing for last {period_hours} hours")

        # Generate tiered briefing
        tiered = await self._tiered_generator.generate(
            period_hours=period_hours,
            user_id=user_id,
            include_so_what=True,
            include_audio=include_audio,
        )

        # Convert to legacy format
        briefing = convert_tiered_to_legacy(tiered)

        # Override title if custom provided
        if custom_title:
            briefing.title = custom_title

        self._logger.info(
            f"Generated briefing {briefing.id} with {len(briefing.sections)} sections"
        )
        return briefing

    async def generate_focused_briefing(
        self,
        topic: str,
        period_hours: int = 24,
        user_id: Optional[str] = None,
    ) -> Briefing:
        """
        Generate a briefing focused on a specific topic.

        Args:
            topic: Topic to focus on
            period_hours: Hours to include
            user_id: Optional user ID

        Returns:
            Focused Briefing object
        """
        self._logger.info(
            f"Generating focused briefing: topic={topic}, period_hours={period_hours}"
        )

        # Generate full tiered briefing
        tiered = await self._tiered_generator.generate(
            period_hours=period_hours,
            user_id=user_id,
            include_so_what=True,
        )

        # Convert to legacy and filter
        briefing = convert_tiered_to_legacy(tiered)

        # Filter sections to match topic
        topic_lower = topic.lower()
        filtered_sections = [
            s for s in briefing.sections
            if topic_lower in s.title.lower() or topic_lower in s.topic.lower()
        ]

        if filtered_sections:
            briefing.sections = filtered_sections
            briefing.title = f"Focused Briefing: {topic.title()}"
            briefing.executive_summary = (
                f"Focused analysis on {topic}. " + briefing.executive_summary[:300]
            )
        else:
            # If no match, keep all sections but update title
            briefing.title = f"Briefing (no specific match for '{topic}')"

        self._logger.info(
            f"Focused briefing complete: id={briefing.id}, "
            f"topic={topic}, sections={len(briefing.sections)}"
        )
        return briefing

    async def generate_tiered(
        self,
        period_hours: int = 24,
        user_id: Optional[str] = None,
        tracked_entities: Optional[List[str]] = None,
        include_audio: bool = False,
    ) -> TieredBriefing:
        """
        Generate a tiered intelligence briefing (native format).

        Use this method when you want the full tiered structure
        with "So What?" analysis and pattern alerts.

        Args:
            period_hours: Hours to cover
            user_id: Optional user ID
            tracked_entities: Entities to prioritize
            include_audio: Whether to generate audio

        Returns:
            TieredBriefing with full tier structure
        """
        return await self._tiered_generator.generate(
            period_hours=period_hours,
            user_id=user_id,
            tracked_entities=tracked_entities,
            include_so_what=True,
            include_audio=include_audio,
        )
