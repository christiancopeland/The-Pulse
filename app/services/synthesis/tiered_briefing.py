"""
Tiered Intelligence Briefing Generator for The Pulse.

SYNTH-004: Tiered Relevance Structure
SYNTH-005: "So What?" Analysis Framework

Implements OSINT professional methodology with actionable intelligence tiers.
Tier priorities are customized per user requirements:
    - Tier 1 (Actionable): Geopolitical/Military
    - Tier 2 (Situational): Local Government
    - Tier 3 (Background): Tech/AI
    - Tier 4 (Monitor): Financial/Business
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.logging import get_logger
from app.services.claude_bridge import claude_structured_output, get_claude_bridge
from app.services.synthesis.context_builder import ContextBuilder, SynthesisContext
from app.services.synthesis.pattern_detector import DetectedPattern
from app.models.news_item import NewsItem

logger = get_logger(__name__)


class IntelligenceTier(IntEnum):
    """Intelligence item priority tiers (customized for user)."""
    TIER_1_ACTIONABLE = 1      # Geopolitical/Military - Immediate attention
    TIER_2_SITUATIONAL = 2     # Local Government - Developing situations
    TIER_3_BACKGROUND = 3      # Tech/AI - Background monitoring
    TIER_4_MONITOR = 4         # Financial/Business - Low priority monitoring


# Topic to Tier mapping based on user priorities
TOPIC_TIER_MAP: Dict[str, IntelligenceTier] = {
    # Tier 1: Geopolitical/Military (Actionable)
    "geopolitics": IntelligenceTier.TIER_1_ACTIONABLE,
    "military": IntelligenceTier.TIER_1_ACTIONABLE,
    "conflict": IntelligenceTier.TIER_1_ACTIONABLE,
    "security": IntelligenceTier.TIER_1_ACTIONABLE,
    "defense": IntelligenceTier.TIER_1_ACTIONABLE,
    "sanctions": IntelligenceTier.TIER_1_ACTIONABLE,
    "diplomacy": IntelligenceTier.TIER_1_ACTIONABLE,

    # Tier 2: Local Government (Situational)
    "local": IntelligenceTier.TIER_2_SITUATIONAL,
    "local_government": IntelligenceTier.TIER_2_SITUATIONAL,
    "regional": IntelligenceTier.TIER_2_SITUATIONAL,
    "zoning": IntelligenceTier.TIER_2_SITUATIONAL,
    "permits": IntelligenceTier.TIER_2_SITUATIONAL,
    "council": IntelligenceTier.TIER_2_SITUATIONAL,
    "municipal": IntelligenceTier.TIER_2_SITUATIONAL,

    # Tier 3: Tech/AI (Background)
    "tech_ai": IntelligenceTier.TIER_3_BACKGROUND,
    "technology": IntelligenceTier.TIER_3_BACKGROUND,
    "science": IntelligenceTier.TIER_3_BACKGROUND,
    "research": IntelligenceTier.TIER_3_BACKGROUND,
    "cyber": IntelligenceTier.TIER_3_BACKGROUND,
    "arxiv": IntelligenceTier.TIER_3_BACKGROUND,

    # Tier 4: Financial/Business (Monitor)
    "financial": IntelligenceTier.TIER_4_MONITOR,
    "business": IntelligenceTier.TIER_4_MONITOR,
    "market": IntelligenceTier.TIER_4_MONITOR,
    "economic": IntelligenceTier.TIER_4_MONITOR,
    "industry": IntelligenceTier.TIER_4_MONITOR,

    # Tier 4: RC/Hobby (Exclude from intelligence analysis - NEVER escalate)
    "rc_industry": IntelligenceTier.TIER_4_MONITOR,
    "rc": IntelligenceTier.TIER_4_MONITOR,
    "hobby": IntelligenceTier.TIER_4_MONITOR,
    "hobbyist": IntelligenceTier.TIER_4_MONITOR,
    "radiocontrol": IntelligenceTier.TIER_4_MONITOR,
    "fpv": IntelligenceTier.TIER_4_MONITOR,
    "rccars": IntelligenceTier.TIER_4_MONITOR,
    "rcplanes": IntelligenceTier.TIER_4_MONITOR,
    "multicopter": IntelligenceTier.TIER_4_MONITOR,
}

# RC/Hobby content identifiers - these should NEVER be escalated to Tier 1
RC_CONTENT_IDENTIFIERS = {
    # Source types
    "source_types": {"rc_manufacturer", "reddit"},
    # Categories that indicate hobby content
    "categories": {"rc_industry", "rc", "hobby", "hobbyist", "radiocontrol", "fpv", "rccars", "rcplanes", "multicopter"},
    # Keywords in title that indicate RC hobby content (not intelligence)
    "title_keywords": {
        "horizon hobby", "traxxas", "spektrum", "arrma", "losi", "axial",
        "fms hobby", "e-flite", "blade", "umx", "bind-n-fly", "bnf",
        "rtf", "pnp", "quadcopter", "fpv drone", "rc car", "rc plane",
        "rc boat", "rc helicopter", "battery lipo", "esc", "servo",
        "transmitter", "receiver", "brushless motor", "radio control",
    },
}

# Keywords that elevate items to Tier 1 regardless of topic
TIER_1_ESCALATION_KEYWORDS = {
    "breaking", "urgent", "attack", "explosion", "killed", "casualties",
    "sanctions", "declared", "invasion", "coup", "emergency", "crisis",
    "missile", "strike", "troops", "deployed", "mobilization", "war",
}


@dataclass
class SoWhatAnalysis:
    """'So What?' analysis for an intelligence item."""
    what_happened: str          # Concise event description
    why_it_matters: str         # Relevance to interests
    what_next: str              # Implications/forecast
    action_items: List[str]     # Actionable recommendations (0-3)
    confidence: float = 0.8     # Analysis confidence (0.0-1.0)


@dataclass
class PatternAlert:
    """Automatically detected pattern alert."""
    alert_type: str             # escalation, network_growth, sentiment_shift, geographic_spread
    entity: Optional[str]       # Entity name if applicable
    description: str            # Human-readable description
    severity: str               # high, medium, low
    metric_change: float        # Percentage or absolute change
    time_window_days: int       # Detection window
    evidence: Dict[str, Any] = field(default_factory=dict)


def convert_detected_pattern_to_alert(pattern: DetectedPattern) -> PatternAlert:
    """Convert a DetectedPattern from pattern_detector to PatternAlert for briefings."""
    # Extract metric_change from evidence if available, otherwise use confidence
    metric_change = pattern.evidence.get("ratio", pattern.confidence)
    if isinstance(metric_change, (int, float)):
        metric_change = float(metric_change)
    else:
        metric_change = pattern.confidence

    return PatternAlert(
        alert_type=pattern.pattern_type.value,  # Convert enum to string
        entity=pattern.entity,
        description=pattern.description,
        severity=pattern.severity,
        metric_change=metric_change,
        time_window_days=pattern.detection_window_days,
        evidence=pattern.evidence,
    )


@dataclass
class TieredBriefingItem:
    """Single item in the tiered intelligence brief."""
    id: str
    tier: IntelligenceTier
    source_type: str            # rss, gdelt, acled, etc.
    source_name: str            # Human-readable source
    title: str
    summary: str
    url: str
    published_at: Optional[datetime]
    collected_at: datetime
    relevance_score: float      # 0.0 - 1.0

    # "So What?" analysis
    analysis: Optional[SoWhatAnalysis] = None

    # Metadata
    entities_mentioned: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    raw_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "tier": self.tier.value,
            "tier_name": self.tier.name,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "relevance_score": self.relevance_score,
            "analysis": asdict(self.analysis) if self.analysis else None,
            "entities_mentioned": self.entities_mentioned,
            "categories": self.categories,
        }


@dataclass
class TieredBriefingSection:
    """Section grouping related items by tier."""
    tier: IntelligenceTier
    name: str                   # e.g., "GEOPOLITICAL & MILITARY"
    items: List[TieredBriefingItem]
    synthesis: str              # LLM-generated section synthesis
    item_count: int
    avg_relevance: float
    collapsed: bool = False     # UI hint: collapse Tier 3/4 by default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "tier_name": self.tier.name,
            "name": self.name,
            "items": [item.to_dict() for item in self.items],
            "synthesis": self.synthesis,
            "item_count": self.item_count,
            "avg_relevance": self.avg_relevance,
            "collapsed": self.collapsed,
        }


@dataclass
class TieredBriefing:
    """Complete tiered intelligence briefing."""
    id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    title: str

    # Pattern alerts (auto-detected) - shown at top
    pattern_alerts: List[PatternAlert]

    # Executive summary (LLM-generated)
    executive_summary: str

    # Sections by tier (ordered Tier 1 -> Tier 4)
    sections: List[TieredBriefingSection]

    # Statistics
    total_items_analyzed: int
    items_by_tier: Dict[int, int]

    # Entity network updates
    entity_highlights: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    audio_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "title": self.title,
            "pattern_alerts": [asdict(a) for a in self.pattern_alerts],
            "executive_summary": self.executive_summary,
            "sections": [s.to_dict() for s in self.sections],
            "total_items_analyzed": self.total_items_analyzed,
            "items_by_tier": self.items_by_tier,
            "entity_highlights": self.entity_highlights,
            "metadata": self.metadata,
            "audio_path": self.audio_path,
        }

    def to_markdown(self) -> str:
        """Convert briefing to markdown format."""
        lines = []

        # Header
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append(f"**Period:** {self.period_start.strftime('%Y-%m-%d %H:%M')} - {self.period_end.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"**Items Analyzed:** {self.total_items_analyzed}")
        lines.append("")

        # Pattern Alerts (if any)
        if self.pattern_alerts:
            lines.append("## PATTERN ALERTS")
            lines.append("")
            for alert in self.pattern_alerts:
                severity_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}.get(alert.severity, "⚪")
                lines.append(f"{severity_icon} **{alert.alert_type.upper()}**: {alert.description}")
            lines.append("")

        # Executive Summary
        lines.append("## EXECUTIVE SUMMARY")
        lines.append("")
        lines.append(self.executive_summary)
        lines.append("")

        # Tier Sections
        tier_headers = {
            IntelligenceTier.TIER_1_ACTIONABLE: "## TIER 1: ACTIONABLE INTELLIGENCE",
            IntelligenceTier.TIER_2_SITUATIONAL: "## TIER 2: SITUATIONAL AWARENESS",
            IntelligenceTier.TIER_3_BACKGROUND: "## TIER 3: BACKGROUND MONITORING",
            IntelligenceTier.TIER_4_MONITOR: "## TIER 4: LOW PRIORITY",
        }

        for section in self.sections:
            lines.append(tier_headers.get(section.tier, f"## {section.name}"))
            lines.append(f"*{section.name} - {section.item_count} items*")
            lines.append("")
            lines.append(section.synthesis)
            lines.append("")

            for item in section.items[:5]:  # Limit items in markdown
                lines.append(f"### {item.title}")
                lines.append(f"*Source: {item.source_name}*")
                lines.append("")
                lines.append(item.summary[:300] + "..." if len(item.summary) > 300 else item.summary)
                lines.append("")

                if item.analysis:
                    lines.append("**So What?**")
                    lines.append(f"- **What happened:** {item.analysis.what_happened}")
                    lines.append(f"- **Why it matters:** {item.analysis.why_it_matters}")
                    lines.append(f"- **What's next:** {item.analysis.what_next}")
                    if item.analysis.action_items:
                        lines.append("- **Actions:**")
                        for action in item.analysis.action_items:
                            lines.append(f"  - {action}")
                    lines.append("")

            if section.item_count > 5:
                lines.append(f"*... and {section.item_count - 5} more items*")
                lines.append("")

        # Entity Highlights
        if self.entity_highlights:
            lines.append("## ENTITY HIGHLIGHTS")
            lines.append("")
            for entity in self.entity_highlights[:10]:
                trend = entity.get("trend", "stable")
                trend_icon = {"rising": "📈", "falling": "📉", "stable": "➡️"}.get(trend, "")
                lines.append(f"- **{entity['name']}**: {entity.get('mention_count', 0)} mentions {trend_icon}")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append(f"*Items by tier: T1={self.items_by_tier.get(1, 0)}, T2={self.items_by_tier.get(2, 0)}, T3={self.items_by_tier.get(3, 0)}, T4={self.items_by_tier.get(4, 0)}*")

        return "\n".join(lines)


class TieredBriefingGenerator:
    """
    Generates professional-grade tiered intelligence briefings.

    Features:
    - Custom tiered relevance structure (Geo/Military > Local Gov > Tech > Financial)
    - "So What?" analysis for high-priority items
    - Automatic pattern detection integration
    - 6-month trend tracking
    - LLM-powered synthesis via Claude Code
    """

    # Tier names for display
    TIER_NAMES = {
        IntelligenceTier.TIER_1_ACTIONABLE: "GEOPOLITICAL & MILITARY",
        IntelligenceTier.TIER_2_SITUATIONAL: "LOCAL GOVERNMENT",
        IntelligenceTier.TIER_3_BACKGROUND: "TECHNOLOGY & AI",
        IntelligenceTier.TIER_4_MONITOR: "FINANCIAL & BUSINESS",
    }

    # System prompt for briefing generation
    BRIEFING_SYSTEM_PROMPT = """You are an intelligence analyst creating a tiered daily briefing.

Your task is to synthesize news items into clear, actionable intelligence.

Guidelines:
1. Be concise and factual - focus on what matters
2. Identify patterns and connections across sources
3. Highlight entities (people, organizations, locations) and their activities
4. Note any emerging trends or concerns
5. Use professional intelligence briefing tone
6. For Tier 1 items, focus on immediate implications
7. For Tier 2 items, focus on local impact
8. For Tier 3/4 items, provide brief summaries only

Structure your response as JSON with the specified format."""

    SO_WHAT_PROMPT = """Analyze this intelligence item using the "So What?" framework.

TITLE: {title}
SOURCE: {source}
CONTENT: {content}

Tracked entities of interest: {entities}

Provide actionable intelligence analysis in JSON format:
{{
    "what_happened": "Concise 1-2 sentence description of the event",
    "why_it_matters": "Why this is relevant to tracked interests or broader significance",
    "what_next": "Potential implications and forecast",
    "action_items": ["Specific actionable recommendation 1", "Recommendation 2"],
    "confidence": 0.8
}}

Be concise. Action items should be specific and practical (0-3 items)."""

    SYNTHESIS_PROMPT = """Synthesize these {tier_name} intelligence items into a brief section summary.

Items:
{items_text}

Entity context:
{entity_context}

Generate a 2-3 paragraph synthesis that:
1. Highlights the most significant developments
2. Notes patterns or connections across items
3. Calls out key entities and their activities
4. For Tier 1: emphasize immediate implications
5. For Tier 2: focus on local/regional impact

Respond with just the synthesis text (no JSON)."""

    EXECUTIVE_SUMMARY_PROMPT = """Create an executive summary for a tiered intelligence briefing.

Pattern Alerts:
{pattern_alerts}

Tier 1 (Geopolitical/Military) Summary:
{tier1_summary}

Tier 2 (Local Government) Summary:
{tier2_summary}

Tier 3 (Tech/AI) Summary:
{tier3_summary}

Entity Highlights:
{entity_highlights}

Generate a concise 2-3 paragraph executive summary that:
1. Leads with the most critical Tier 1 developments
2. Highlights any pattern alerts requiring attention
3. Notes significant local government activity
4. Briefly mentions noteworthy tech developments

Respond with just the summary text."""

    def __init__(
        self,
        db_session: AsyncSession,
        pattern_detector: Optional["PatternDetector"] = None
    ):
        self.db = db_session
        self.context_builder = ContextBuilder(db_session)
        self._bridge = get_claude_bridge(timeout_seconds=180)
        self._pattern_detector = pattern_detector
        self._logger = get_logger(f"{__name__}.TieredBriefingGenerator")

    async def generate(
        self,
        period_hours: int = 24,
        user_id: Optional[str] = None,
        tracked_entities: Optional[List[str]] = None,
        include_so_what: bool = True,
        include_audio: bool = False,
        max_items_per_tier: int = 50,
    ) -> TieredBriefing:
        """
        Generate a complete tiered intelligence briefing.

        Args:
            period_hours: Time period to cover
            user_id: Optional user ID for entity context
            tracked_entities: Entities to prioritize in analysis
            include_so_what: Whether to generate "So What?" analysis for Tier 1/2
            include_audio: Whether to generate audio version
            max_items_per_tier: Max items to include per tier

        Returns:
            Complete TieredBriefing
        """
        self._logger.info(f"Generating tiered briefing for last {period_hours} hours")

        # Calculate time period
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(hours=period_hours)

        # Build context
        context = await self.context_builder.build(
            period_start=period_start,
            period_end=period_end,
            user_id=user_id,
            include_entities=user_id is not None,
            max_items=500,  # Get more items for tiering
        )

        if not context.news_items:
            self._logger.warning("No news items found for briefing period")
            return self._empty_briefing(period_start, period_end)

        # 1. Classify items by tier
        tiered_items = await self._classify_items(context.news_items)

        # 2. Detect patterns (if detector available)
        pattern_alerts: List[PatternAlert] = []
        if self._pattern_detector:
            detected_patterns = await self._pattern_detector.detect_all_patterns(
                [item.to_dict() for item in context.news_items],
                tracked_entities=tracked_entities,
            )
            # Convert DetectedPattern objects to PatternAlert objects
            pattern_alerts = [
                convert_detected_pattern_to_alert(p) for p in detected_patterns
            ]

        # 3. Generate "So What?" analysis for Tier 1/2 items
        if include_so_what:
            await self._add_so_what_analysis(
                tiered_items,
                tracked_entities or [],
                max_tier=IntelligenceTier.TIER_2_SITUATIONAL
            )

        # 4. Generate section syntheses
        sections = await self._generate_sections(
            tiered_items,
            context,
            max_items_per_tier
        )

        # 5. Generate executive summary
        executive_summary = await self._generate_executive_summary(
            sections, pattern_alerts, context
        )

        # 6. Format entity highlights
        entity_highlights = self._format_entity_highlights(context)

        # Calculate stats
        items_by_tier = {
            tier.value: len(items)
            for tier, items in tiered_items.items()
        }

        briefing = TieredBriefing(
            id=str(uuid4()),
            generated_at=datetime.now(timezone.utc),
            period_start=period_start,
            period_end=period_end,
            title=f"Intelligence Briefing: {period_end.strftime('%Y-%m-%d')}",
            pattern_alerts=pattern_alerts,
            executive_summary=executive_summary,
            sections=sections,
            total_items_analyzed=len(context.news_items),
            items_by_tier=items_by_tier,
            entity_highlights=entity_highlights,
            metadata={
                "period_hours": period_hours,
                "sources": list(context.temporal.items_by_source.keys()),
                "user_id": user_id,
                "include_so_what": include_so_what,
            },
        )

        # Generate audio if requested
        if include_audio:
            try:
                from app.services.synthesis.audio_generator import AudioGenerator
                audio_gen = AudioGenerator()
                audio_path = await audio_gen.generate(
                    briefing.to_markdown(),
                    briefing.id
                )
                briefing.audio_path = audio_path
            except Exception as e:
                self._logger.warning(f"Audio generation failed: {e}")

        self._logger.info(
            f"Generated tiered briefing {briefing.id}: "
            f"T1={items_by_tier.get(1, 0)}, T2={items_by_tier.get(2, 0)}, "
            f"T3={items_by_tier.get(3, 0)}, T4={items_by_tier.get(4, 0)}"
        )

        return briefing

    async def _classify_items(
        self,
        items: List[NewsItem]
    ) -> Dict[IntelligenceTier, List[TieredBriefingItem]]:
        """Classify news items into intelligence tiers."""
        tiered: Dict[IntelligenceTier, List[TieredBriefingItem]] = {
            tier: [] for tier in IntelligenceTier
        }

        for item in items:
            tier = self._determine_tier(item)

            briefing_item = TieredBriefingItem(
                id=str(item.id),
                tier=tier,
                source_type=item.source_type or "unknown",
                source_name=item.source_name or "Unknown",
                title=item.title or "Untitled",
                summary=item.summary or item.content[:500] if item.content else "",
                url=item.url or "",
                published_at=item.published_at,
                collected_at=item.collected_at or datetime.now(timezone.utc),
                relevance_score=item.relevance_score or 0.0,
                categories=item.categories or [],
                raw_content=item.content,
            )

            tiered[tier].append(briefing_item)

        # Sort each tier by relevance score
        for tier in tiered:
            tiered[tier].sort(key=lambda x: x.relevance_score, reverse=True)

        return tiered

    def _is_rc_hobby_content(self, item: NewsItem) -> bool:
        """Check if an item is RC/hobby content that should never be escalated."""
        title_lower = (item.title or "").lower()
        source_type = (item.source_type or "").lower()
        source_name = (item.source_name or "").lower()
        categories = [c.lower() for c in (item.categories or [])]

        # Check source type
        if source_type in RC_CONTENT_IDENTIFIERS["source_types"]:
            return True

        # Check categories
        if any(cat in RC_CONTENT_IDENTIFIERS["categories"] for cat in categories):
            return True

        # Check title for RC brand/product keywords
        if any(kw in title_lower for kw in RC_CONTENT_IDENTIFIERS["title_keywords"]):
            return True

        # Check source name for RC manufacturers
        rc_source_names = {"horizon hobby", "traxxas", "big squid rc", "fms hobby", "rcgroups"}
        if any(name in source_name for name in rc_source_names):
            return True

        return False

    def _determine_tier(self, item: NewsItem) -> IntelligenceTier:
        """Determine the intelligence tier for an item."""
        title_lower = (item.title or "").lower()
        content_lower = (item.content or "").lower()
        categories = item.categories or []
        source_type = (item.source_type or "").lower()

        # CRITICAL: Check for RC/hobby content FIRST - these NEVER get escalated
        # This prevents false positives from hobby content using military-adjacent terms
        # like "attack" (attack run), "strike" (strike competition), etc.
        if self._is_rc_hobby_content(item):
            return IntelligenceTier.TIER_4_MONITOR

        # Check for Tier 1 escalation keywords (override other classifications)
        # Only applies to non-RC content
        combined_text = f"{title_lower} {content_lower}"
        if any(keyword in combined_text for keyword in TIER_1_ESCALATION_KEYWORDS):
            return IntelligenceTier.TIER_1_ACTIONABLE

        # Check categories against topic-tier map
        for cat in categories:
            cat_lower = cat.lower()
            if cat_lower in TOPIC_TIER_MAP:
                return TOPIC_TIER_MAP[cat_lower]

        # Check source type
        source_tier_map = {
            "gdelt": IntelligenceTier.TIER_1_ACTIONABLE,
            "acled": IntelligenceTier.TIER_1_ACTIONABLE,
            "opensanctions": IntelligenceTier.TIER_1_ACTIONABLE,
            "local": IntelligenceTier.TIER_2_SITUATIONAL,
            "rss": IntelligenceTier.TIER_2_SITUATIONAL,
            "arxiv": IntelligenceTier.TIER_3_BACKGROUND,
            "sec_edgar": IntelligenceTier.TIER_4_MONITOR,
            "rc_manufacturer": IntelligenceTier.TIER_4_MONITOR,
            "reddit": IntelligenceTier.TIER_4_MONITOR,
        }
        if source_type in source_tier_map:
            return source_tier_map[source_type]

        # Check title for topic keywords
        for topic, tier in TOPIC_TIER_MAP.items():
            if topic in title_lower:
                return tier

        # Default to Tier 3 (Background)
        return IntelligenceTier.TIER_3_BACKGROUND

    async def _add_so_what_analysis(
        self,
        tiered_items: Dict[IntelligenceTier, List[TieredBriefingItem]],
        tracked_entities: List[str],
        max_tier: IntelligenceTier = IntelligenceTier.TIER_2_SITUATIONAL
    ):
        """Add 'So What?' analysis to high-priority items."""
        entities_str = ", ".join(tracked_entities[:10]) if tracked_entities else "None specified"

        for tier in IntelligenceTier:
            if tier.value > max_tier.value:
                continue  # Skip lower-priority tiers

            for item in tiered_items[tier][:5]:  # Limit to top 5 per tier
                try:
                    analysis = await self._generate_so_what(item, entities_str)
                    item.analysis = analysis
                except Exception as e:
                    self._logger.warning(f"So What analysis failed for {item.id}: {e}")

    async def _generate_so_what(
        self,
        item: TieredBriefingItem,
        entities_str: str
    ) -> SoWhatAnalysis:
        """Generate 'So What?' analysis for an item."""
        content = item.raw_content or item.summary
        if len(content) > 2000:
            content = content[:2000] + "..."

        prompt = self.SO_WHAT_PROMPT.format(
            title=item.title,
            source=item.source_name,
            content=content,
            entities=entities_str,
        )

        messages = [
            {"role": "system", "content": "You are an intelligence analyst. Be concise and actionable."},
            {"role": "user", "content": prompt},
        ]

        schema = {
            "type": "object",
            "properties": {
                "what_happened": {"type": "string"},
                "why_it_matters": {"type": "string"},
                "what_next": {"type": "string"},
                "action_items": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
            },
            "required": ["what_happened", "why_it_matters", "what_next", "action_items"]
        }

        result = await claude_structured_output(messages, schema)

        return SoWhatAnalysis(
            what_happened=result.get("what_happened", "Analysis unavailable"),
            why_it_matters=result.get("why_it_matters", ""),
            what_next=result.get("what_next", ""),
            action_items=result.get("action_items", [])[:3],
            confidence=result.get("confidence", 0.8),
        )

    async def _generate_sections(
        self,
        tiered_items: Dict[IntelligenceTier, List[TieredBriefingItem]],
        context: SynthesisContext,
        max_items: int
    ) -> List[TieredBriefingSection]:
        """Generate briefing sections for each tier."""
        sections = []

        for tier in IntelligenceTier:
            items = tiered_items[tier][:max_items]

            if not items:
                continue

            # Generate synthesis for this tier
            synthesis = await self._generate_tier_synthesis(tier, items, context)

            # Calculate average relevance
            avg_relevance = (
                sum(item.relevance_score for item in items) / len(items)
                if items else 0.0
            )

            sections.append(TieredBriefingSection(
                tier=tier,
                name=self.TIER_NAMES.get(tier, "UNKNOWN"),
                items=items,
                synthesis=synthesis,
                item_count=len(tiered_items[tier]),  # Total count, not limited
                avg_relevance=avg_relevance,
                collapsed=tier.value >= IntelligenceTier.TIER_3_BACKGROUND.value,
            ))

        return sections

    async def _generate_tier_synthesis(
        self,
        tier: IntelligenceTier,
        items: List[TieredBriefingItem],
        context: SynthesisContext
    ) -> str:
        """Generate synthesis for a single tier."""
        if not items:
            return "No items to report."

        try:
            # Format items for prompt
            items_text = "\n\n".join([
                f"- **{item.title}** ({item.source_name}): {item.summary[:200]}..."
                if len(item.summary) > 200 else f"- **{item.title}** ({item.source_name}): {item.summary}"
                for item in items[:10]
            ])

            # Format entity context
            entity_context = "No specific entities tracked."
            if context.entities:
                entity_context = "\n".join([
                    f"- {e.name} ({e.entity_type}): {e.mention_count} mentions"
                    for e in context.entities[:5]
                ])

            prompt = self.SYNTHESIS_PROMPT.format(
                tier_name=self.TIER_NAMES.get(tier, "INTELLIGENCE"),
                items_text=items_text,
                entity_context=entity_context,
            )

            messages = [
                {"role": "system", "content": self.BRIEFING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = await self._bridge.query(messages)
            return response["content"].strip() or f"Analysis of {len(items)} {self.TIER_NAMES.get(tier, '')} items."

        except Exception as e:
            self._logger.error(f"Synthesis generation failed for {tier.name}: {e}")
            return f"Analysis of {len(items)} items. Key topics: {', '.join(item.title[:30] for item in items[:3])}."

    async def _generate_executive_summary(
        self,
        sections: List[TieredBriefingSection],
        pattern_alerts: List[PatternAlert],
        context: SynthesisContext
    ) -> str:
        """Generate the executive summary."""
        if not sections:
            return "No significant developments to report."

        try:
            # Format pattern alerts
            alerts_text = "None detected."
            if pattern_alerts:
                alerts_text = "\n".join([
                    f"- {a.alert_type.upper()}: {a.description} (severity: {a.severity})"
                    for a in pattern_alerts[:5]
                ])

            # Get tier summaries
            tier_summaries = {tier: "" for tier in IntelligenceTier}
            for section in sections:
                tier_summaries[section.tier] = section.synthesis[:300] + "..." if len(section.synthesis) > 300 else section.synthesis

            # Format entity highlights
            entity_text = "No specific entities tracked."
            if context.entities:
                entity_text = "\n".join([
                    f"- {e.name}: {e.mention_count} mentions ({e.trend})"
                    for e in context.entities[:5]
                ])

            prompt = self.EXECUTIVE_SUMMARY_PROMPT.format(
                pattern_alerts=alerts_text,
                tier1_summary=tier_summaries.get(IntelligenceTier.TIER_1_ACTIONABLE, "No Tier 1 items."),
                tier2_summary=tier_summaries.get(IntelligenceTier.TIER_2_SITUATIONAL, "No Tier 2 items."),
                tier3_summary=tier_summaries.get(IntelligenceTier.TIER_3_BACKGROUND, "No Tier 3 items."),
                entity_highlights=entity_text,
            )

            messages = [
                {"role": "system", "content": self.BRIEFING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = await self._bridge.query(messages)
            return response["content"].strip() or "Summary generation in progress."

        except Exception as e:
            self._logger.error(f"Executive summary generation failed: {e}")
            # Fallback summary
            tier_counts = ", ".join([
                f"{self.TIER_NAMES.get(s.tier, 'Unknown')}: {s.item_count} items"
                for s in sections
            ])
            return f"This briefing covers developments across {len(sections)} tiers. {tier_counts}."

    def _format_entity_highlights(
        self,
        context: SynthesisContext
    ) -> List[Dict[str, Any]]:
        """Format entity highlights for the briefing."""
        highlights = []

        for entity in context.entities[:10]:
            highlights.append({
                "name": entity.name,
                "entity_type": entity.entity_type,
                "mention_count": entity.mention_count,
                "trend": entity.trend,
                "sources": entity.sources[:3],
            })

        return highlights

    def _empty_briefing(
        self,
        period_start: datetime,
        period_end: datetime
    ) -> TieredBriefing:
        """Return an empty briefing when no items found."""
        return TieredBriefing(
            id=str(uuid4()),
            generated_at=datetime.now(timezone.utc),
            period_start=period_start,
            period_end=period_end,
            title=f"Intelligence Briefing: {period_end.strftime('%Y-%m-%d')}",
            pattern_alerts=[],
            executive_summary="No significant developments to report for this period.",
            sections=[],
            total_items_analyzed=0,
            items_by_tier={1: 0, 2: 0, 3: 0, 4: 0},
            entity_highlights=[],
            metadata={"empty": True},
        )
