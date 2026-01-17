"""
Context Builder for synthesis operations.

SYNTH-001: Builds entity and temporal context for briefing generation.

Aggregates information from:
- Collected news items
- Tracked entities and their mentions
- Entity relationships
- Temporal patterns

Updated 2026-01-05: Now handles unprocessed items by calculating relevance on-the-fly.
This ensures briefings work immediately after collection without waiting for processing pipeline.
"""
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
import logging
from collections import defaultdict

from sqlalchemy import select, and_, func, not_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news_item import NewsItem
from app.models.entities import TrackedEntity, EntityMention
from app.services.processing.ranker import RelevanceRanker, RankingConfig

logger = logging.getLogger(__name__)

# Quality filtering configuration
MIN_RELEVANCE_SCORE = 0.4  # Minimum relevance score for briefing inclusion
EXCLUDED_SOURCE_TYPES: Set[str] = {"rc_manufacturer"}
EXCLUDED_CATEGORIES: Set[str] = {"rc_industry", "rc", "hobby", "hobbyist"}


@dataclass
class EntityContext:
    """Context for a single entity."""
    entity_id: str
    name: str
    entity_type: str
    mention_count: int
    sources: List[str] = field(default_factory=list)
    recent_mentions: List[Dict[str, Any]] = field(default_factory=list)
    related_entities: List[str] = field(default_factory=list)
    trend: str = "stable"  # rising, falling, stable


@dataclass
class TemporalContext:
    """Context for a time period."""
    period_start: datetime
    period_end: datetime
    total_items: int
    items_by_source: Dict[str, int] = field(default_factory=dict)
    items_by_category: Dict[str, int] = field(default_factory=dict)
    top_topics: List[str] = field(default_factory=list)


@dataclass
class SynthesisContext:
    """Complete context for synthesis."""
    temporal: TemporalContext
    entities: List[EntityContext] = field(default_factory=list)
    news_items: List[NewsItem] = field(default_factory=list)
    grouped_by_topic: Dict[str, List[NewsItem]] = field(default_factory=dict)


class ContextBuilder:
    """
    Builds context for briefing synthesis.

    Aggregates entities, mentions, and news items from a time period
    to provide rich context for LLM-based synthesis.
    """

    # Category mapping for topic grouping
    TOPIC_CATEGORIES = {
        "geopolitics": ["world", "politics", "international", "conflict", "diplomacy"],
        "tech_ai": ["technology", "ai", "machine learning", "software", "research"],
        "security": ["security", "cybersecurity", "crime", "law enforcement"],
        "local": ["local", "regional", "community"],
        "science": ["science", "research", "academic", "arxiv"],
        "industry": ["business", "industry", "manufacturing", "product"],
    }

    def __init__(self, db_session: AsyncSession):
        """
        Initialize context builder.

        Args:
            db_session: Async database session
        """
        self.db = db_session
        self._logger = logging.getLogger(f"{__name__}.ContextBuilder")

    async def build(
        self,
        period_start: datetime,
        period_end: datetime,
        user_id: Optional[str] = None,
        include_entities: bool = True,
        max_items: int = 100,
    ) -> SynthesisContext:
        """
        Build complete synthesis context for a time period.

        Args:
            period_start: Start of the period
            period_end: End of the period
            user_id: Optional user ID for entity filtering
            include_entities: Whether to include entity context
            max_items: Maximum news items to include

        Returns:
            SynthesisContext with all aggregated data
        """
        self._logger.info(
            f"Building context for period {period_start} to {period_end}"
        )

        # Fetch news items from the period
        news_items = await self._fetch_news_items(period_start, period_end, max_items)

        # Build temporal context
        temporal_context = self._build_temporal_context(
            news_items, period_start, period_end
        )

        # Group items by topic
        grouped = self._group_by_topic(news_items)

        # Build entity context if requested
        entity_contexts = []
        if include_entities and user_id:
            entity_contexts = await self._build_entity_context(
                user_id, period_start, period_end, news_items
            )

        return SynthesisContext(
            temporal=temporal_context,
            entities=entity_contexts,
            news_items=news_items,
            grouped_by_topic=grouped,
        )

    async def _fetch_news_items(
        self,
        period_start: datetime,
        period_end: datetime,
        max_items: int
    ) -> List[NewsItem]:
        """
        Fetch news items from the time period with quality filtering.

        Applies filters to exclude:
        - RC/hobby source types
        - RC/hobby categories

        For unprocessed items (processed != 1), calculates relevance on-the-fly
        using the RelevanceRanker to ensure newly collected content is included.
        """
        # Fetch ALL items from the period (not just processed ones)
        # We'll calculate relevance on-the-fly for unprocessed items
        query = (
            select(NewsItem)
            .where(
                and_(
                    NewsItem.collected_at >= period_start,
                    NewsItem.collected_at <= period_end,
                    not_(NewsItem.source_type.in_(EXCLUDED_SOURCE_TYPES)),  # Exclude RC sources
                )
            )
            .order_by(NewsItem.collected_at.desc())
            .limit(max_items * 4)  # Fetch more since we'll filter by relevance
        )

        result = await self.db.execute(query)
        all_items = list(result.scalars().all())

        self._logger.debug(f"Fetched {len(all_items)} raw items from period")

        # Filter out RC hobby categories
        category_filtered = []
        for item in all_items:
            item_categories = set(c.lower() for c in (item.categories or []))
            if not item_categories.intersection(EXCLUDED_CATEGORIES):
                category_filtered.append(item)

        self._logger.debug(f"After category filter: {len(category_filtered)} items")

        # For items without relevance scores, calculate them on-the-fly
        ranker = RelevanceRanker()
        items_with_scores = []

        for item in category_filtered:
            # Use existing score if processed, otherwise calculate
            if item.processed == 1 and item.relevance_score is not None and item.relevance_score > 0:
                score = item.relevance_score
            else:
                # Calculate relevance on-the-fly
                ranking_result = await ranker.score(item)
                score = ranking_result.score
                # Optionally update the item's score (won't persist without commit)
                item.relevance_score = score

            if score >= MIN_RELEVANCE_SCORE:
                items_with_scores.append((item, score))

        self._logger.debug(f"After relevance filter (>={MIN_RELEVANCE_SCORE}): {len(items_with_scores)} items")

        # Sort by score descending and take top items
        items_with_scores.sort(key=lambda x: x[1], reverse=True)
        filtered_items = [item for item, _ in items_with_scores[:max_items]]

        self._logger.info(
            f"Fetched {len(filtered_items)} news items for period "
            f"(from {len(all_items)} total, {len(category_filtered)} after category filter)"
        )
        return filtered_items

    def _build_temporal_context(
        self,
        items: List[NewsItem],
        period_start: datetime,
        period_end: datetime
    ) -> TemporalContext:
        """Build temporal context from news items."""
        items_by_source: Dict[str, int] = defaultdict(int)
        items_by_category: Dict[str, int] = defaultdict(int)

        for item in items:
            items_by_source[item.source_name or "Unknown"] += 1
            for cat in (item.categories or []):
                items_by_category[cat] += 1

        # Determine top topics based on category counts
        sorted_categories = sorted(
            items_by_category.items(),
            key=lambda x: x[1],
            reverse=True
        )
        top_topics = [cat for cat, _ in sorted_categories[:5]]

        return TemporalContext(
            period_start=period_start,
            period_end=period_end,
            total_items=len(items),
            items_by_source=dict(items_by_source),
            items_by_category=dict(items_by_category),
            top_topics=top_topics,
        )

    def _group_by_topic(
        self,
        items: List[NewsItem]
    ) -> Dict[str, List[NewsItem]]:
        """Group news items by topic category."""
        grouped: Dict[str, List[NewsItem]] = defaultdict(list)

        for item in items:
            topic = self._determine_topic(item)
            grouped[topic].append(item)

        return dict(grouped)

    def _determine_topic(self, item: NewsItem) -> str:
        """Determine the primary topic for a news item."""
        categories = item.categories or []
        source_type = item.source_type or ""
        title = (item.title or "").lower()

        # Check against topic categories
        for topic, keywords in self.TOPIC_CATEGORIES.items():
            for keyword in keywords:
                if keyword in source_type.lower():
                    return topic
                if any(keyword in cat.lower() for cat in categories):
                    return topic
                if keyword in title:
                    return topic

        # Default categorization based on source type
        source_map = {
            "rss": "news",
            "gdelt": "geopolitics",
            "arxiv": "science",
            "reddit": "community",
            "local": "local",
        }
        return source_map.get(source_type, "general")

    async def _build_entity_context(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
        news_items: List[NewsItem]
    ) -> List[EntityContext]:
        """Build context for tracked entities."""
        # Fetch user's tracked entities
        entity_query = select(TrackedEntity).where(
            TrackedEntity.user_id == user_id
        )
        result = await self.db.execute(entity_query)
        entities = result.scalars().all()

        if not entities:
            return []

        entity_contexts = []
        news_item_ids = [str(item.id) for item in news_items]

        for entity in entities:
            # Get mentions in the news items from this period
            mention_query = select(EntityMention).where(
                and_(
                    EntityMention.entity_id == entity.entity_id,
                    EntityMention.news_item_id.in_(news_item_ids)
                )
            )
            mention_result = await self.db.execute(mention_query)
            mentions = mention_result.scalars().all()

            if not mentions:
                continue

            # Collect unique sources
            sources = set()
            recent_mentions = []
            for mention in mentions[:5]:  # Limit recent mentions
                # Find the corresponding news item
                for item in news_items:
                    if str(item.id) == mention.news_item_id:
                        sources.add(item.source_name or "Unknown")
                        recent_mentions.append({
                            "context": mention.context,
                            "source": item.source_name,
                            "title": item.title,
                            "timestamp": mention.timestamp,
                        })
                        break

            # Calculate trend (simplified)
            trend = "stable"
            if len(mentions) > 5:
                trend = "rising"
            elif len(mentions) < 2:
                trend = "falling"

            entity_contexts.append(EntityContext(
                entity_id=str(entity.entity_id),
                name=entity.name,
                entity_type=entity.entity_type,
                mention_count=len(mentions),
                sources=list(sources),
                recent_mentions=recent_mentions,
                related_entities=[],  # TODO: Add relationship analysis
                trend=trend,
            ))

        # Sort by mention count
        entity_contexts.sort(key=lambda e: e.mention_count, reverse=True)
        return entity_contexts

    async def get_entity_summary(
        self,
        entity_name: str,
        user_id: str,
        days: int = 7
    ) -> Optional[EntityContext]:
        """
        Get detailed context for a specific entity.

        Args:
            entity_name: Name of the entity
            user_id: User ID
            days: Number of days to look back

        Returns:
            EntityContext or None if not found
        """
        period_end = datetime.now(timezone.utc)
        period_start = period_end - timedelta(days=days)

        # Find the entity
        entity_query = select(TrackedEntity).where(
            and_(
                TrackedEntity.user_id == user_id,
                TrackedEntity.name_lower == entity_name.lower()
            )
        )
        result = await self.db.execute(entity_query)
        entity = result.scalar_one_or_none()

        if not entity:
            return None

        # Build context just for this entity
        context = await self.build(
            period_start=period_start,
            period_end=period_end,
            user_id=user_id,
            include_entities=True,
        )

        # Find the entity in the context
        for ec in context.entities:
            if ec.entity_id == str(entity.entity_id):
                return ec

        return None

    def format_for_prompt(self, context: SynthesisContext) -> str:
        """
        Format context as text for LLM prompts.

        Args:
            context: SynthesisContext to format

        Returns:
            Formatted string for prompt injection
        """
        parts = []

        # Temporal summary
        parts.append(f"## Time Period")
        parts.append(
            f"Period: {context.temporal.period_start.strftime('%Y-%m-%d %H:%M')} "
            f"to {context.temporal.period_end.strftime('%Y-%m-%d %H:%M')}"
        )
        parts.append(f"Total items analyzed: {context.temporal.total_items}")

        if context.temporal.top_topics:
            parts.append(f"Top topics: {', '.join(context.temporal.top_topics)}")

        # Source breakdown
        if context.temporal.items_by_source:
            parts.append("\n## Sources")
            for source, count in sorted(
                context.temporal.items_by_source.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]:
                parts.append(f"- {source}: {count} items")

        # Entity highlights
        if context.entities:
            parts.append("\n## Key Entities")
            for entity in context.entities[:10]:
                trend_indicator = {
                    "rising": "↑",
                    "falling": "↓",
                    "stable": "→"
                }.get(entity.trend, "→")

                parts.append(
                    f"- **{entity.name}** ({entity.entity_type}): "
                    f"{entity.mention_count} mentions {trend_indicator}"
                )

        # Topic breakdown
        if context.grouped_by_topic:
            parts.append("\n## Topics")
            for topic, items in sorted(
                context.grouped_by_topic.items(),
                key=lambda x: len(x[1]),
                reverse=True
            ):
                parts.append(f"- {topic.title()}: {len(items)} items")

        return "\n".join(parts)
