"""
6-Month Trend Indicator Service for The Pulse.

SYNTH-008: Rolling Trend Indicators

Provides rolling statistics and trend indicators for intelligence metrics:
- Conflict Index: Weighted measure of conflict events
- Market Volatility: Financial event frequency
- Political Instability: Political turmoil events
- Entity Activity: Mentions of tracked entities
- Collection Health: Data collection system status
"""
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import statistics

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case, cast, Date

from app.core.logging import get_logger
from app.models.news_item import NewsItem, CollectionRun
from app.models.entities import TrackedEntity, EntityMention

logger = get_logger(__name__)


class TrendDirection(Enum):
    """Direction of trend movement."""
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"


class AlertLevel(Enum):
    """Alert level based on deviation from baseline."""
    NORMAL = "normal"
    ELEVATED = "elevated"
    CRITICAL = "critical"


@dataclass
class TrendIndicator:
    """A single trend indicator with computed metrics."""
    name: str
    description: str
    current_value: float
    baseline_value: float
    change_percent: float
    direction: TrendDirection
    alert_level: AlertLevel
    sparkline_data: List[float] = field(default_factory=list)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "current_value": round(self.current_value, 2),
            "baseline_value": round(self.baseline_value, 2),
            "change_percent": round(self.change_percent, 2),
            "direction": self.direction.value,
            "alert_level": self.alert_level.value,
            "sparkline_data": [round(v, 1) for v in self.sparkline_data],
            "last_updated": self.last_updated.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class TrendSnapshot:
    """Complete snapshot of all trend indicators."""
    generated_at: datetime
    period_days: int
    baseline_days: int
    indicators: Dict[str, TrendIndicator]
    summary: str
    overall_status: AlertLevel

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "period_days": self.period_days,
            "baseline_days": self.baseline_days,
            "indicators": {k: v.to_dict() for k, v in self.indicators.items()},
            "summary": self.summary,
            "overall_status": self.overall_status.value,
        }


class TrendIndicatorService:
    """
    Computes 6-month rolling trend indicators for intelligence metrics.

    Indicators Computed:
    - Conflict Index: Events tagged with conflict/military/violence categories
    - Market Volatility: Financial/business/market event frequency
    - Political Instability: Political turmoil/governance events
    - Entity Activity: Mentions of user's tracked entities
    - Collection Health: Data collection success rate

    Each indicator includes:
    - Current value (last 30 days)
    - Baseline value (6-month average per 30-day period)
    - Change percentage from baseline
    - Direction (rising/falling/stable)
    - Alert level (normal/elevated/critical)
    - Sparkline data (daily counts for visualization)
    """

    # Category definitions for each index
    CONFLICT_CATEGORIES = [
        "conflict", "military", "violence", "security", "defense",
        "war", "attack", "casualties", "armed_conflict"
    ]
    FINANCIAL_CATEGORIES = [
        "financial", "market", "business", "economic", "trade",
        "banking", "investment", "commerce"
    ]
    POLITICAL_CATEGORIES = [
        "political", "governance", "election", "government",
        "diplomacy", "policy", "legislative", "regulatory"
    ]
    TECH_CATEGORIES = [
        "tech_ai", "technology", "science", "research", "cyber",
        "innovation", "digital"
    ]

    # Thresholds for alert levels
    ELEVATED_THRESHOLD = 25.0   # 25% increase from baseline
    CRITICAL_THRESHOLD = 50.0  # 50% increase from baseline
    STABLE_THRESHOLD = 5.0     # Within 5% considered stable

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self._logger = get_logger(f"{__name__}.TrendIndicatorService")

    async def compute_all_indicators(
        self,
        user_id: Optional[str] = None,
        period_days: int = 30,
        baseline_days: int = 180
    ) -> TrendSnapshot:
        """
        Compute all trend indicators.

        Args:
            user_id: Optional user ID for entity-specific indicators
            period_days: Days for current period (default 30)
            baseline_days: Days for baseline calculation (default 180)

        Returns:
            TrendSnapshot with all indicators
        """
        self._logger.info(f"Computing trend indicators (period={period_days}d, baseline={baseline_days}d)")

        indicators = {}

        # Compute each indicator
        indicators["conflict_index"] = await self._compute_category_index(
            name="Conflict Index",
            description="Armed conflict, military activity, and security events",
            categories=self.CONFLICT_CATEGORIES,
            period_days=period_days,
            baseline_days=baseline_days
        )

        indicators["market_volatility"] = await self._compute_category_index(
            name="Market Volatility",
            description="Financial, business, and economic event activity",
            categories=self.FINANCIAL_CATEGORIES,
            period_days=period_days,
            baseline_days=baseline_days
        )

        indicators["political_instability"] = await self._compute_category_index(
            name="Political Instability",
            description="Political turmoil, governance, and election events",
            categories=self.POLITICAL_CATEGORIES,
            period_days=period_days,
            baseline_days=baseline_days
        )

        indicators["tech_activity"] = await self._compute_category_index(
            name="Tech Activity",
            description="Technology, AI, and cyber event activity",
            categories=self.TECH_CATEGORIES,
            period_days=period_days,
            baseline_days=baseline_days
        )

        # Entity activity (user-specific)
        indicators["entity_activity"] = await self._compute_entity_activity(
            user_id=user_id,
            period_days=period_days,
            baseline_days=baseline_days
        )

        # Collection health
        indicators["collection_health"] = await self._compute_collection_health(
            period_days=period_days
        )

        # Determine overall status
        overall_status = self._compute_overall_status(indicators)

        # Generate summary
        summary = self._generate_summary(indicators)

        snapshot = TrendSnapshot(
            generated_at=datetime.now(timezone.utc),
            period_days=period_days,
            baseline_days=baseline_days,
            indicators=indicators,
            summary=summary,
            overall_status=overall_status
        )

        self._logger.info(f"Trend indicators computed: overall_status={overall_status.value}")
        return snapshot

    async def _compute_category_index(
        self,
        name: str,
        description: str,
        categories: List[str],
        period_days: int,
        baseline_days: int
    ) -> TrendIndicator:
        """Compute trend indicator for a set of categories."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)
        baseline_start = now - timedelta(days=baseline_days)

        # Get current period count
        current_count = await self._count_items_by_category(
            categories, period_start, now
        )

        # Get baseline count (full baseline period)
        baseline_total = await self._count_items_by_category(
            categories, baseline_start, now
        )

        # Calculate baseline per period (average monthly rate)
        periods_in_baseline = baseline_days / period_days
        baseline_value = baseline_total / periods_in_baseline if periods_in_baseline > 0 else 0

        # Calculate change
        change_percent = self._calculate_change_percent(current_count, baseline_value)

        # Determine direction and alert level
        direction = self._determine_direction(change_percent)
        alert_level = self._determine_alert_level(change_percent)

        # Get sparkline data (daily counts for last 30 days)
        sparkline = await self._get_daily_counts(categories, period_start, now)

        return TrendIndicator(
            name=name,
            description=description,
            current_value=current_count,
            baseline_value=baseline_value,
            change_percent=change_percent,
            direction=direction,
            alert_level=alert_level,
            sparkline_data=sparkline,
            metadata={
                "categories": categories,
                "period_days": period_days,
                "baseline_days": baseline_days,
            }
        )

    async def _count_items_by_category(
        self,
        categories: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> int:
        """Count news items matching categories within date range."""
        try:
            # Build category match conditions
            # Categories is JSONB array, need to check if any category matches
            category_conditions = []
            for cat in categories:
                # Check if the category exists in the JSONB array
                category_conditions.append(
                    NewsItem.categories.contains([cat])
                )

            if not category_conditions:
                return 0

            # Also check if categories overlap via source_type for some items
            source_conditions = []
            source_type_map = {
                "conflict": ["acled", "gdelt"],
                "military": ["gdelt"],
                "financial": ["sec_edgar"],
                "tech_ai": ["arxiv"],
            }
            for cat in categories:
                if cat in source_type_map:
                    for source in source_type_map[cat]:
                        source_conditions.append(NewsItem.source_type == source)

            from sqlalchemy import or_

            # Combine all conditions
            all_conditions = category_conditions + source_conditions

            query = select(func.count(NewsItem.id)).where(
                and_(
                    NewsItem.collected_at >= start_date,
                    NewsItem.collected_at <= end_date,
                    or_(*all_conditions) if all_conditions else True
                )
            )

            result = await self.db.execute(query)
            count = result.scalar() or 0
            return count

        except Exception as e:
            self._logger.error(f"Error counting items by category: {e}")
            return 0

    async def _get_daily_counts(
        self,
        categories: List[str],
        start_date: datetime,
        end_date: datetime
    ) -> List[float]:
        """Get daily counts for sparkline visualization."""
        try:
            # Build category conditions similar to above
            from sqlalchemy import or_

            category_conditions = []
            for cat in categories:
                category_conditions.append(NewsItem.categories.contains([cat]))

            source_conditions = []
            source_type_map = {
                "conflict": ["acled", "gdelt"],
                "military": ["gdelt"],
                "financial": ["sec_edgar"],
                "tech_ai": ["arxiv"],
            }
            for cat in categories:
                if cat in source_type_map:
                    for source in source_type_map[cat]:
                        source_conditions.append(NewsItem.source_type == source)

            all_conditions = category_conditions + source_conditions

            # Group by date
            query = select(
                cast(NewsItem.collected_at, Date).label('date'),
                func.count(NewsItem.id).label('count')
            ).where(
                and_(
                    NewsItem.collected_at >= start_date,
                    NewsItem.collected_at <= end_date,
                    or_(*all_conditions) if all_conditions else True
                )
            ).group_by(
                cast(NewsItem.collected_at, Date)
            ).order_by(
                cast(NewsItem.collected_at, Date)
            )

            result = await self.db.execute(query)
            rows = result.fetchall()

            # Build daily counts array (fill gaps with 0)
            daily_counts = defaultdict(int)
            for row in rows:
                daily_counts[row.date] = row.count

            # Generate continuous date range
            sparkline = []
            current = start_date.date()
            end = end_date.date()
            while current <= end:
                sparkline.append(float(daily_counts.get(current, 0)))
                current += timedelta(days=1)

            return sparkline[-30:]  # Last 30 days

        except Exception as e:
            self._logger.error(f"Error getting daily counts: {e}")
            return []

    async def _compute_entity_activity(
        self,
        user_id: Optional[str],
        period_days: int,
        baseline_days: int
    ) -> TrendIndicator:
        """Compute entity mention activity indicator."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)
        baseline_start = now - timedelta(days=baseline_days)

        current_count = 0
        baseline_total = 0
        sparkline = []
        tracked_count = 0

        if user_id:
            try:
                from uuid import UUID
                user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

                # Count current period mentions
                current_query = select(func.count(EntityMention.mention_id)).where(
                    and_(
                        EntityMention.user_id == user_uuid,
                        EntityMention.timestamp >= period_start.isoformat()
                    )
                )
                result = await self.db.execute(current_query)
                current_count = result.scalar() or 0

                # Count baseline mentions
                baseline_query = select(func.count(EntityMention.mention_id)).where(
                    and_(
                        EntityMention.user_id == user_uuid,
                        EntityMention.timestamp >= baseline_start.isoformat()
                    )
                )
                result = await self.db.execute(baseline_query)
                baseline_total = result.scalar() or 0

                # Count tracked entities
                entity_query = select(func.count(TrackedEntity.entity_id)).where(
                    TrackedEntity.user_id == user_uuid
                )
                result = await self.db.execute(entity_query)
                tracked_count = result.scalar() or 0

            except Exception as e:
                self._logger.error(f"Error computing entity activity: {e}")

        # Calculate baseline per period
        periods_in_baseline = baseline_days / period_days if period_days > 0 else 1
        baseline_value = baseline_total / periods_in_baseline if periods_in_baseline > 0 else 0

        # Calculate metrics
        change_percent = self._calculate_change_percent(current_count, baseline_value)
        direction = self._determine_direction(change_percent)
        alert_level = self._determine_alert_level(change_percent)

        return TrendIndicator(
            name="Entity Activity",
            description="Tracked entity mention frequency",
            current_value=float(current_count),
            baseline_value=baseline_value,
            change_percent=change_percent,
            direction=direction,
            alert_level=alert_level,
            sparkline_data=sparkline,
            metadata={
                "user_id": user_id,
                "tracked_entities": tracked_count,
                "period_days": period_days,
            }
        )

    async def _compute_collection_health(
        self,
        period_days: int
    ) -> TrendIndicator:
        """Compute data collection health indicator."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)

        try:
            # Count successful runs
            success_query = select(func.count(CollectionRun.id)).where(
                and_(
                    CollectionRun.started_at >= period_start,
                    CollectionRun.status == "completed"
                )
            )
            result = await self.db.execute(success_query)
            success_count = result.scalar() or 0

            # Count total runs
            total_query = select(func.count(CollectionRun.id)).where(
                CollectionRun.started_at >= period_start
            )
            result = await self.db.execute(total_query)
            total_count = result.scalar() or 0

            # Calculate success rate
            success_rate = (success_count / total_count * 100) if total_count > 0 else 100.0

            # Determine health level
            if success_rate >= 95:
                alert_level = AlertLevel.NORMAL
                direction = TrendDirection.STABLE
            elif success_rate >= 80:
                alert_level = AlertLevel.ELEVATED
                direction = TrendDirection.FALLING
            else:
                alert_level = AlertLevel.CRITICAL
                direction = TrendDirection.FALLING

            # Get items collected
            items_query = select(func.sum(CollectionRun.items_new)).where(
                and_(
                    CollectionRun.started_at >= period_start,
                    CollectionRun.status == "completed"
                )
            )
            result = await self.db.execute(items_query)
            items_collected = result.scalar() or 0

            return TrendIndicator(
                name="Collection Health",
                description="Data collection system success rate",
                current_value=success_rate,
                baseline_value=95.0,  # Target 95% success
                change_percent=success_rate - 95.0,
                direction=direction,
                alert_level=alert_level,
                sparkline_data=[],
                metadata={
                    "successful_runs": success_count,
                    "total_runs": total_count,
                    "items_collected": items_collected,
                    "period_days": period_days,
                }
            )

        except Exception as e:
            self._logger.error(f"Error computing collection health: {e}")
            return TrendIndicator(
                name="Collection Health",
                description="Data collection system success rate",
                current_value=0,
                baseline_value=95.0,
                change_percent=-95.0,
                direction=TrendDirection.FALLING,
                alert_level=AlertLevel.CRITICAL,
                metadata={"error": str(e)}
            )

    def _calculate_change_percent(
        self,
        current: float,
        baseline: float
    ) -> float:
        """Calculate percentage change from baseline."""
        if baseline == 0:
            return 100.0 if current > 0 else 0.0
        return ((current - baseline) / baseline) * 100

    def _determine_direction(self, change_percent: float) -> TrendDirection:
        """Determine trend direction from change percentage."""
        if change_percent > self.STABLE_THRESHOLD:
            return TrendDirection.RISING
        elif change_percent < -self.STABLE_THRESHOLD:
            return TrendDirection.FALLING
        return TrendDirection.STABLE

    def _determine_alert_level(self, change_percent: float) -> AlertLevel:
        """Determine alert level from change percentage."""
        abs_change = abs(change_percent)
        if abs_change >= self.CRITICAL_THRESHOLD:
            return AlertLevel.CRITICAL
        elif abs_change >= self.ELEVATED_THRESHOLD:
            return AlertLevel.ELEVATED
        return AlertLevel.NORMAL

    def _compute_overall_status(
        self,
        indicators: Dict[str, TrendIndicator]
    ) -> AlertLevel:
        """Compute overall status from all indicators."""
        # If any indicator is critical, overall is critical
        for indicator in indicators.values():
            if indicator.alert_level == AlertLevel.CRITICAL:
                return AlertLevel.CRITICAL

        # If any indicator is elevated, overall is elevated
        for indicator in indicators.values():
            if indicator.alert_level == AlertLevel.ELEVATED:
                return AlertLevel.ELEVATED

        return AlertLevel.NORMAL

    def _generate_summary(
        self,
        indicators: Dict[str, TrendIndicator]
    ) -> str:
        """Generate human-readable summary of indicators."""
        summaries = []

        # Check for critical indicators
        critical = [
            name for name, ind in indicators.items()
            if ind.alert_level == AlertLevel.CRITICAL
        ]
        if critical:
            summaries.append(f"CRITICAL: {', '.join(critical)} require attention")

        # Check for elevated indicators
        elevated = [
            name for name, ind in indicators.items()
            if ind.alert_level == AlertLevel.ELEVATED
        ]
        if elevated:
            summaries.append(f"ELEVATED: {', '.join(elevated)} above normal")

        # Notable trends
        rising = [
            f"{name} (+{ind.change_percent:.0f}%)"
            for name, ind in indicators.items()
            if ind.direction == TrendDirection.RISING and ind.change_percent > 20
        ]
        if rising:
            summaries.append(f"Rising: {', '.join(rising)}")

        falling = [
            f"{name} ({ind.change_percent:.0f}%)"
            for name, ind in indicators.items()
            if ind.direction == TrendDirection.FALLING and ind.change_percent < -20
        ]
        if falling:
            summaries.append(f"Falling: {', '.join(falling)}")

        if not summaries:
            summaries.append("All indicators within normal parameters")

        return " | ".join(summaries)

    async def get_indicator_history(
        self,
        indicator_name: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get historical values for a specific indicator.

        This would typically be stored in a separate table.
        For now, returns computed values based on available data.
        """
        # This would ideally query a trend_history table
        # For now, return empty list as placeholder
        return []

    async def get_category_breakdown(
        self,
        period_days: int = 30
    ) -> Dict[str, int]:
        """Get breakdown of items by category for the period."""
        now = datetime.now(timezone.utc)
        period_start = now - timedelta(days=period_days)

        try:
            # Query source_type counts as a proxy for category
            query = select(
                NewsItem.source_type,
                func.count(NewsItem.id).label('count')
            ).where(
                NewsItem.collected_at >= period_start
            ).group_by(
                NewsItem.source_type
            )

            result = await self.db.execute(query)
            rows = result.fetchall()

            return {row.source_type: row.count for row in rows}

        except Exception as e:
            self._logger.error(f"Error getting category breakdown: {e}")
            return {}
