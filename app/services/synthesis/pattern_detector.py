"""
Pattern Detection Engine for Intelligence Briefings.

SYNTH-006: Automatic Pattern Detection

Detects emerging patterns in intelligence data:
- Escalation: Increasing event frequency
- Network Growth: Expanding entity relationships
- Sentiment Shift: Changing tone toward entities
- Geographic Spread: Events spreading to new locations
- Temporal Clustering: Events clustering in unusual time windows
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import statistics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.core.logging import get_logger
from app.models.news_item import NewsItem
from app.models.entities import TrackedEntity, EntityMention

logger = get_logger(__name__)


class PatternType(Enum):
    """Types of patterns the detector can identify."""
    ESCALATION = "escalation"
    NETWORK_GROWTH = "network_growth"
    SENTIMENT_SHIFT = "sentiment_shift"
    GEOGRAPHIC_SPREAD = "geographic_spread"
    TEMPORAL_CLUSTERING = "temporal_clustering"
    ENTITY_SURGE = "entity_surge"


@dataclass
class DetectedPattern:
    """A detected pattern with evidence."""
    pattern_type: PatternType
    severity: str               # high, medium, low
    entity: Optional[str]       # Related entity if applicable
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    detection_window_days: int = 7
    confidence: float = 0.7     # 0.0 - 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value,
            "severity": self.severity,
            "entity": self.entity,
            "description": self.description,
            "evidence": self.evidence,
            "detection_window_days": self.detection_window_days,
            "confidence": self.confidence,
        }


class PatternDetector:
    """
    Detects emerging patterns in intelligence data.

    Used by TieredBriefingGenerator to surface automatic alerts
    that appear at the top of briefings.

    Pattern Types:
    - Escalation: Increasing event frequency by category
    - Network Growth: Expanding entity relationship networks
    - Sentiment Shift: Changing tone toward tracked entities
    - Geographic Spread: Events spreading to new locations
    - Temporal Clustering: Events clustering in unusual time windows
    - Entity Surge: Sudden increase in entity mentions
    """

    # Detection thresholds
    ESCALATION_THRESHOLD = 1.5      # 50% increase triggers detection
    NETWORK_GROWTH_THRESHOLD = 0.25  # 25% new connections
    SENTIMENT_SHIFT_THRESHOLD = 0.3  # 30% tone change
    GEOGRAPHIC_SPREAD_THRESHOLD = 2  # 2+ new locations
    ENTITY_SURGE_THRESHOLD = 3.0     # 3x normal mention rate

    def __init__(self, db_session: Optional[AsyncSession] = None):
        self.db = db_session
        self._logger = get_logger(f"{__name__}.PatternDetector")

    async def detect_all_patterns(
        self,
        items: List[Dict[str, Any]],
        tracked_entities: Optional[List[str]] = None,
        window_days: int = 7
    ) -> List[DetectedPattern]:
        """
        Run all pattern detectors on the data.

        Args:
            items: List of news item dicts (from NewsItem.to_dict())
            tracked_entities: Entities to focus on
            window_days: Detection window

        Returns:
            List of detected patterns sorted by severity
        """
        self._logger.info(f"Running pattern detection on {len(items)} items")
        patterns = []

        # Run each detector
        patterns.extend(await self._detect_escalation(items, window_days))
        patterns.extend(await self._detect_temporal_clustering(items))

        if tracked_entities:
            patterns.extend(await self._detect_entity_surge(items, tracked_entities, window_days))
            patterns.extend(await self._detect_sentiment_shift(items, tracked_entities, window_days))

        if self.db:
            patterns.extend(await self._detect_network_growth(tracked_entities, window_days))

        patterns.extend(await self._detect_geographic_spread(items, window_days))

        # Sort by severity (high first)
        severity_order = {"high": 0, "medium": 1, "low": 2}
        patterns.sort(key=lambda p: (severity_order.get(p.severity, 3), -p.confidence))

        self._logger.info(f"Detected {len(patterns)} patterns")
        return patterns

    async def _detect_escalation(
        self,
        items: List[Dict[str, Any]],
        window_days: int
    ) -> List[DetectedPattern]:
        """Detect escalating event frequency by category."""
        patterns = []

        # Group items by category
        category_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"current": 0, "previous": 0})
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=window_days)
        previous_start = window_start - timedelta(days=window_days)

        for item in items:
            pub_date = self._parse_datetime(item.get("published_at") or item.get("collected_at"))
            if not pub_date:
                continue

            categories = item.get("categories", [])
            if isinstance(categories, str):
                categories = [categories]
            if not categories:
                categories = ["uncategorized"]

            for cat in categories:
                if pub_date >= window_start:
                    category_counts[cat]["current"] += 1
                elif pub_date >= previous_start:
                    category_counts[cat]["previous"] += 1

        # Check for escalation
        for category, counts in category_counts.items():
            if counts["previous"] >= 3:  # Need baseline
                ratio = counts["current"] / counts["previous"]
                if ratio >= self.ESCALATION_THRESHOLD:
                    severity = "high" if ratio >= 2.5 else "medium" if ratio >= 2.0 else "low"
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.ESCALATION,
                        severity=severity,
                        entity=None,
                        description=f"'{category}' events increased {ratio:.1f}x over {window_days} days ({counts['previous']} -> {counts['current']})",
                        evidence={
                            "current_count": counts["current"],
                            "previous_count": counts["previous"],
                            "ratio": ratio,
                            "category": category,
                        },
                        detection_window_days=window_days,
                        confidence=min(0.9, 0.5 + (counts["current"] / 50)),
                    ))

        return patterns

    async def _detect_entity_surge(
        self,
        items: List[Dict[str, Any]],
        tracked_entities: List[str],
        window_days: int
    ) -> List[DetectedPattern]:
        """Detect sudden surge in entity mentions."""
        patterns = []
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=window_days)
        previous_start = window_start - timedelta(days=window_days)

        entity_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"current": 0, "previous": 0})

        for item in items:
            pub_date = self._parse_datetime(item.get("published_at") or item.get("collected_at"))
            if not pub_date:
                continue

            content = f"{item.get('title', '')} {item.get('content', '')} {item.get('summary', '')}".lower()

            for entity in tracked_entities:
                if entity.lower() in content:
                    if pub_date >= window_start:
                        entity_counts[entity]["current"] += 1
                    elif pub_date >= previous_start:
                        entity_counts[entity]["previous"] += 1

        for entity, counts in entity_counts.items():
            if counts["previous"] >= 2:  # Need baseline
                ratio = counts["current"] / counts["previous"]
                if ratio >= self.ENTITY_SURGE_THRESHOLD:
                    severity = "high" if ratio >= 5.0 else "medium"
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.ENTITY_SURGE,
                        severity=severity,
                        entity=entity,
                        description=f"'{entity}' mentions surged {ratio:.1f}x ({counts['previous']} -> {counts['current']})",
                        evidence={
                            "entity": entity,
                            "current_mentions": counts["current"],
                            "previous_mentions": counts["previous"],
                            "ratio": ratio,
                        },
                        detection_window_days=window_days,
                        confidence=min(0.9, 0.5 + (counts["current"] / 30)),
                    ))

        return patterns

    async def _detect_sentiment_shift(
        self,
        items: List[Dict[str, Any]],
        tracked_entities: List[str],
        window_days: int
    ) -> List[DetectedPattern]:
        """Detect changing sentiment toward tracked entities."""
        patterns = []

        # Group items mentioning each entity
        entity_sentiments: Dict[str, List[float]] = defaultdict(list)

        for item in items:
            content = f"{item.get('title', '')} {item.get('content', item.get('summary', ''))}".lower()
            metadata = item.get("metadata", {}) or {}

            # Use GDELT tone if available
            tone = metadata.get("tone", 0)
            if tone == 0:
                # Simple sentiment heuristic based on keywords
                tone = self._estimate_sentiment(content)

            for entity in tracked_entities:
                if entity.lower() in content:
                    entity_sentiments[entity].append(tone)

        for entity, tones in entity_sentiments.items():
            if len(tones) >= 6:  # Need enough samples
                mid = len(tones) // 2
                early_avg = statistics.mean(tones[:mid])
                late_avg = statistics.mean(tones[mid:])
                shift = late_avg - early_avg

                if abs(shift) >= self.SENTIMENT_SHIFT_THRESHOLD:
                    direction = "positive" if shift > 0 else "negative"
                    severity = "high" if abs(shift) >= 0.5 else "medium"
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.SENTIMENT_SHIFT,
                        severity=severity,
                        entity=entity,
                        description=f"Sentiment toward '{entity}' shifted {direction} by {abs(shift):.2f}",
                        evidence={
                            "entity": entity,
                            "early_sentiment": round(early_avg, 3),
                            "late_sentiment": round(late_avg, 3),
                            "shift": round(shift, 3),
                            "direction": direction,
                            "sample_size": len(tones),
                        },
                        detection_window_days=window_days,
                        confidence=min(0.8, len(tones) / 20),
                    ))

        return patterns

    async def _detect_network_growth(
        self,
        tracked_entities: Optional[List[str]],
        window_days: int
    ) -> List[DetectedPattern]:
        """Detect expanding entity relationship networks."""
        patterns = []

        if not self.db or not tracked_entities:
            return patterns

        # This requires querying entity_mentions table to find co-occurrences
        # Simplified implementation - would need relationship table for full version

        return patterns

    async def _detect_geographic_spread(
        self,
        items: List[Dict[str, Any]],
        window_days: int
    ) -> List[DetectedPattern]:
        """Detect events spreading to new geographic locations."""
        patterns = []

        # Track locations by event type/category
        # This requires location extraction from items
        # Using metadata from GDELT/ACLED which include location data

        location_by_category: Dict[str, Dict[str, set]] = defaultdict(lambda: {"current": set(), "previous": set()})
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=window_days)
        previous_start = window_start - timedelta(days=window_days)

        for item in items:
            pub_date = self._parse_datetime(item.get("published_at") or item.get("collected_at"))
            if not pub_date:
                continue

            metadata = item.get("metadata", {}) or {}
            location = metadata.get("location") or metadata.get("country") or metadata.get("admin1")
            if not location:
                continue

            categories = item.get("categories", [])
            if isinstance(categories, str):
                categories = [categories]

            for cat in categories:
                if pub_date >= window_start:
                    location_by_category[cat]["current"].add(location)
                elif pub_date >= previous_start:
                    location_by_category[cat]["previous"].add(location)

        for category, locations in location_by_category.items():
            new_locations = locations["current"] - locations["previous"]
            if len(new_locations) >= self.GEOGRAPHIC_SPREAD_THRESHOLD:
                severity = "high" if len(new_locations) >= 4 else "medium"
                patterns.append(DetectedPattern(
                    pattern_type=PatternType.GEOGRAPHIC_SPREAD,
                    severity=severity,
                    entity=None,
                    description=f"'{category}' events spread to {len(new_locations)} new locations: {', '.join(list(new_locations)[:5])}",
                    evidence={
                        "category": category,
                        "new_locations": list(new_locations)[:10],
                        "new_location_count": len(new_locations),
                        "previous_locations": len(locations["previous"]),
                        "current_locations": len(locations["current"]),
                    },
                    detection_window_days=window_days,
                    confidence=0.75,
                ))

        return patterns

    async def _detect_temporal_clustering(
        self,
        items: List[Dict[str, Any]]
    ) -> List[DetectedPattern]:
        """Detect events clustering in unusual time windows."""
        patterns = []

        # Group items by hour
        hourly_counts: Dict[str, int] = defaultdict(int)

        for item in items:
            pub_date = self._parse_datetime(item.get("published_at") or item.get("collected_at"))
            if not pub_date:
                continue
            hourly_counts[pub_date.strftime("%Y-%m-%d %H:00")] += 1

        # Detect spikes (> 2 standard deviations)
        if len(hourly_counts) >= 6:
            counts = list(hourly_counts.values())
            mean = statistics.mean(counts)
            stdev = statistics.stdev(counts) if len(counts) > 1 else 0

            for hour, count in hourly_counts.items():
                if stdev > 0 and count > mean + (2.5 * stdev) and count >= 10:
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.TEMPORAL_CLUSTERING,
                        severity="low",
                        entity=None,
                        description=f"Unusual event spike at {hour}: {count} events (avg: {mean:.1f})",
                        evidence={
                            "hour": hour,
                            "count": count,
                            "mean": round(mean, 2),
                            "stdev": round(stdev, 2),
                            "z_score": round((count - mean) / stdev, 2) if stdev > 0 else 0,
                        },
                        detection_window_days=1,
                        confidence=0.7,
                    ))

        return patterns

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _estimate_sentiment(self, text: str) -> float:
        """Simple sentiment estimation based on keyword presence."""
        positive_words = {"success", "growth", "positive", "agreement", "peace", "cooperation", "progress", "approved"}
        negative_words = {"attack", "killed", "crisis", "failed", "conflict", "violence", "threat", "sanctions", "rejected"}

        text_lower = text.lower()
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        if positive_count + negative_count == 0:
            return 0.0

        return (positive_count - negative_count) / (positive_count + negative_count)
