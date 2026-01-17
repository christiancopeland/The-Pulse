"""
Relevance ranking for collected news items.

Calculates relevance scores based on source credibility,
recency, category importance, and entity mentions.

PROC-003: Relevance Ranking
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime, timezone, timedelta
import logging
import re

from app.models.news_item import NewsItem
from app.services.collectors.config import SOURCE_PRIORITY, CATEGORY_LABELS

logger = logging.getLogger(__name__)


@dataclass
class RankingConfig:
    """Configuration for relevance ranking."""
    # Weight factors (should sum to 1.0)
    source_weight: float = 0.25
    recency_weight: float = 0.30
    category_weight: float = 0.20
    entity_weight: float = 0.15
    content_weight: float = 0.10

    # Recency decay settings
    recency_half_life_hours: float = 24.0  # Score halves after this time
    recency_max_age_hours: float = 168.0  # 1 week max

    # Source credibility scores (0-10)
    # Intelligence sources scored high, RC/hobby sources scored near-zero
    source_scores: Dict[str, float] = field(default_factory=lambda: {
        # Intelligence sources (high credibility)
        "reuters": 10.0,
        "ap": 10.0,
        "bbc": 9.5,
        "gdelt": 9.0,
        "acled": 9.5,
        "opensanctions": 9.0,
        "sec_edgar": 8.5,

        # Academic/Research
        "arxiv": 9.0,

        # AI Provider blogs (high credibility - primary sources)
        "openai": 9.5,
        "google_ai": 9.0,
        "deepmind": 9.5,
        "huggingface": 8.5,
        "nvidia": 8.5,
        "stability": 8.0,

        # Security news (high credibility)
        "hacker_news_security": 8.0,  # TheHackerNews (not YC HN)
        "bleeping_computer": 8.0,
        "the_register": 7.5,
        "dark_reading": 7.5,

        # Federal law enforcement (official government sources)
        "fbi": 10.0,

        # National security analysis (high credibility)
        "just_security": 9.0,
        "cipher_brief": 8.5,
        "long_war_journal": 8.5,

        # Think tanks (high credibility - expert analysis)
        "csis": 9.0,
        "rand": 9.5,
        "atlantic_council": 8.5,

        # Academic preprints & science journals (high credibility)
        "biorxiv": 8.5,
        "medrxiv": 8.5,
        "nature": 10.0,
        "science": 10.0,

        # Tech news
        "ars_technica": 7.5,
        "hacker_news": 7.0,

        # Local news
        "chattanoogan": 8.0,
        "wrcb": 8.0,
        "wdef": 8.0,

        # RC/Hobby sources (reduced to near-zero to exclude from briefings)
        "horizon_hobby": 1.0,  # Was 7.0
        "traxxas": 1.0,        # Was 7.0
        "fms_hobby": 1.0,      # Was 7.0
        "big_squid_rc": 1.0,   # Was 6.5
        "rcgroups": 1.0,

        # Reddit (low for hobby subreddits, handled by category)
        "reddit": 3.0,         # Was 5.0
    })

    # Category importance (0-10)
    # Intelligence categories scored high, RC/hobby categories near-zero
    category_importance: Dict[str, float] = field(default_factory=lambda: {
        # Intelligence categories (high importance)
        "geopolitics": 9.5,
        "military": 9.5,
        "conflict": 9.0,
        "crime_international": 9.0,
        "crime_national": 9.0,  # Increased for federal law enforcement content
        "crime_local": 8.5,
        "sanctions": 9.0,
        "cyber": 9.0,  # Increased for CISA and security advisory content

        # Tech/Research
        "tech_ai": 8.5,  # Increased for AI provider blog content
        "tech_general": 7.0,
        "research": 8.0,  # Increased for academic preprint content

        # Local news
        "local": 7.5,

        # Financial (lower priority per user specs)
        "financial": 6.5,
        "business": 6.0,

        # Weather
        "weather": 5.0,

        # RC/Hobby categories (near-zero to effectively exclude)
        "rc_industry": 0.5,    # Was 6.0
        "rc": 0.5,
        "hobby": 0.5,
        "hobbyist": 0.5,
        "radiocontrol": 0.5,
        "fpv": 0.5,
        "rccars": 0.5,
        "rcplanes": 0.5,
        "multicopter": 0.5,
    })


@dataclass
class RankingResult:
    """Result of relevance ranking."""
    item_id: str
    score: float  # 0.0 to 1.0
    components: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return f"<RankingResult(id={self.item_id[:8]}, score={self.score:.3f})>"


class RelevanceRanker:
    """
    Calculates relevance scores for news items.

    Scoring factors:
    - Source credibility: Trusted sources score higher
    - Recency: Newer items score higher (exponential decay)
    - Category importance: Priority categories score higher
    - Entity mentions: Items mentioning tracked entities score higher
    - Content quality: Longer, better-structured content scores higher
    """

    def __init__(self, config: Optional[RankingConfig] = None, tracked_entities: Optional[Set[str]] = None):
        """
        Initialize ranker.

        Args:
            config: Optional RankingConfig override
            tracked_entities: Set of entity names being tracked (lowercase)
        """
        self.config = config or RankingConfig()
        self.tracked_entities = tracked_entities or set()
        self._logger = logging.getLogger(f"{__name__}.RelevanceRanker")

        # Compile source name patterns for matching
        self._source_patterns = {
            name: re.compile(re.escape(name), re.I)
            for name in self.config.source_scores.keys()
        }

    def update_tracked_entities(self, entities: Set[str]):
        """Update the set of tracked entities."""
        self.tracked_entities = {e.lower() for e in entities}

    async def score(self, item: NewsItem) -> RankingResult:
        """
        Calculate relevance score for a news item.

        Args:
            item: NewsItem to score

        Returns:
            RankingResult with score and component breakdown
        """
        components = {}

        # Calculate each component
        components["source"] = self._score_source(item)
        components["recency"] = self._score_recency(item)
        components["category"] = self._score_category(item)
        components["entity"] = self._score_entities(item)
        components["content"] = self._score_content(item)

        # Calculate weighted score
        cfg = self.config
        score = (
            components["source"] * cfg.source_weight +
            components["recency"] * cfg.recency_weight +
            components["category"] * cfg.category_weight +
            components["entity"] * cfg.entity_weight +
            components["content"] * cfg.content_weight
        )

        return RankingResult(
            item_id=str(item.id),
            score=min(1.0, max(0.0, score)),
            components=components,
            metadata={
                "source_name": item.source_name,
                "categories": item.categories,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
        )

    def _score_source(self, item: NewsItem) -> float:
        """Score based on source credibility."""
        source_name = (item.source_name or "").lower()

        # Try to match against known sources
        for name, pattern in self._source_patterns.items():
            if pattern.search(source_name):
                score = self.config.source_scores[name] / 10.0
                return score

        # Unknown source gets middle score
        return 0.5

    def _score_recency(self, item: NewsItem) -> float:
        """Score based on how recent the item is (exponential decay)."""
        if not item.published_at:
            # No publish date, use collected_at or give middle score
            pub_time = item.collected_at or datetime.now(timezone.utc)
        else:
            pub_time = item.published_at

        # Ensure timezone aware
        if pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_hours = (now - pub_time).total_seconds() / 3600

        # Cap at max age
        if age_hours > self.config.recency_max_age_hours:
            return 0.0

        # Exponential decay
        half_life = self.config.recency_half_life_hours
        decay_factor = 0.5 ** (age_hours / half_life)

        return decay_factor

    def _score_category(self, item: NewsItem) -> float:
        """Score based on category importance."""
        categories = item.categories or []

        if not categories:
            return 0.5

        # Get highest importance among categories
        max_importance = 0.0
        for category in categories:
            importance = self.config.category_importance.get(category.lower(), 5.0)
            max_importance = max(max_importance, importance)

        return max_importance / 10.0

    def _score_entities(self, item: NewsItem) -> float:
        """Score based on tracked entity mentions."""
        if not self.tracked_entities:
            return 0.5  # No entities tracked, neutral score

        content = f"{item.title or ''} {item.content or ''} {item.summary or ''}".lower()

        if not content.strip():
            return 0.3

        # Count entity mentions
        mentions = 0
        for entity in self.tracked_entities:
            if entity in content:
                mentions += 1

        if mentions == 0:
            return 0.3  # No tracked entities mentioned

        # Score increases with mentions (diminishing returns)
        # 1 mention = 0.6, 2 = 0.75, 3 = 0.85, 4+ = 0.95
        if mentions == 1:
            return 0.6
        elif mentions == 2:
            return 0.75
        elif mentions == 3:
            return 0.85
        else:
            return 0.95

    def _score_content(self, item: NewsItem) -> float:
        """Score based on content quality and length."""
        content = item.content or item.summary or ""

        if not content:
            return 0.3

        length = len(content)

        # Length scoring (diminishing returns)
        if length < 100:
            length_score = 0.3
        elif length < 500:
            length_score = 0.5
        elif length < 1000:
            length_score = 0.7
        elif length < 3000:
            length_score = 0.85
        else:
            length_score = 0.95

        # Structure scoring (presence of paragraphs)
        paragraphs = content.count('\n\n') + 1
        if paragraphs >= 3:
            structure_score = 1.0
        elif paragraphs >= 2:
            structure_score = 0.8
        else:
            structure_score = 0.6

        return (length_score * 0.7 + structure_score * 0.3)

    async def rank_batch(self, items: List[NewsItem]) -> List[RankingResult]:
        """
        Rank a batch of items and return sorted by score.

        Args:
            items: List of NewsItem to rank

        Returns:
            List of RankingResult sorted by score (descending)
        """
        results = []
        for item in items:
            try:
                result = await self.score(item)
                results.append(result)
            except Exception as e:
                self._logger.error(f"Error ranking item {item.id}: {e}")
                results.append(RankingResult(
                    item_id=str(item.id),
                    score=0.0,
                    metadata={"error": str(e)}
                ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def apply_scores(self, items: List[NewsItem], results: List[RankingResult]) -> None:
        """
        Apply ranking scores to news items in-place.

        Args:
            items: List of NewsItem
            results: Corresponding RankingResult list
        """
        result_map = {r.item_id: r.score for r in results}
        for item in items:
            item_id = str(item.id)
            if item_id in result_map:
                item.relevance_score = result_map[item_id]

    def get_top_items(
        self,
        items: List[NewsItem],
        results: List[RankingResult],
        top_n: int = 10,
        min_score: float = 0.0
    ) -> List[NewsItem]:
        """
        Get top-ranked items.

        Args:
            items: List of NewsItem
            results: Corresponding RankingResult list
            top_n: Number of top items to return
            min_score: Minimum score threshold

        Returns:
            List of top-ranked NewsItem
        """
        # Build ID to item mapping
        item_map = {str(item.id): item for item in items}

        # Filter and sort results
        filtered = [r for r in results if r.score >= min_score]
        filtered.sort(key=lambda r: r.score, reverse=True)

        # Get top items
        top_items = []
        for result in filtered[:top_n]:
            if result.item_id in item_map:
                top_items.append(item_map[result.item_id])

        return top_items
