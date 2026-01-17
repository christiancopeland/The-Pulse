"""
Local Intelligence Analyzer for The Pulse.

Analyzes local government data to generate insights, summaries,
and briefings about activity in monitored areas.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text

from app.models.local_government import (
    CouncilMeeting, ZoningCase, BuildingPermit,
    PropertyTransaction, LocalCourtCase
)

logger = logging.getLogger(__name__)


class LocalIntelligenceAnalyzer:
    """
    Analyze local government data for insights and briefings.

    Provides:
    - Activity summaries
    - Trend analysis
    - Council meeting analysis
    - Development pattern detection
    """

    def __init__(
        self,
        db_session: AsyncSession,
        ollama_client=None,
        user_id: Optional[UUID] = None
    ):
        """
        Initialize the analyzer.

        Args:
            db_session: Async SQLAlchemy session
            ollama_client: Optional Ollama client for LLM analysis
            user_id: User ID for filtering
        """
        self.db = db_session
        self.ollama = ollama_client
        self.user_id = user_id

    async def generate_local_briefing(self, days: int = 7) -> Dict:
        """
        Generate comprehensive local government briefing.

        Args:
            days: Number of days to cover

        Returns:
            Briefing dictionary with sections
        """
        # Use naive datetime for PostgreSQL TIMESTAMP WITHOUT TIME ZONE columns
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

        briefing = {
            "period": f"Last {days} days",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sections": {}
        }

        # Council activity
        council_summary = await self._summarize_council_activity(cutoff)
        if council_summary:
            briefing["sections"]["council"] = council_summary

        # Zoning activity
        zoning_summary = await self._summarize_zoning_activity(cutoff)
        if zoning_summary:
            briefing["sections"]["zoning"] = zoning_summary

        # Permit activity
        permit_summary = await self._summarize_permit_activity(cutoff)
        if permit_summary:
            briefing["sections"]["permits"] = permit_summary

        # Property transactions
        property_summary = await self._summarize_property_activity(cutoff)
        if property_summary:
            briefing["sections"]["property"] = property_summary

        # Court activity
        court_summary = await self._summarize_court_activity(cutoff)
        if court_summary:
            briefing["sections"]["court"] = court_summary

        # Generate LLM summary if available
        if self.ollama:
            briefing["executive_summary"] = await self._generate_executive_summary(briefing)

        return briefing

    async def _summarize_council_activity(self, cutoff: datetime) -> Optional[Dict]:
        """Summarize council meeting activity."""
        query = select(CouncilMeeting).where(
            CouncilMeeting.meeting_date >= cutoff
        ).order_by(CouncilMeeting.meeting_date.desc())

        result = await self.db.execute(query)
        meetings = result.scalars().all()

        if not meetings:
            return None

        # Group by jurisdiction
        by_jurisdiction = defaultdict(list)
        for meeting in meetings:
            by_jurisdiction[meeting.jurisdiction].append({
                "date": meeting.meeting_date.isoformat() if meeting.meeting_date else None,
                "body": meeting.body,
                "type": meeting.meeting_type,
                "agenda_items": len(meeting.agenda_items or []),
                "summary": meeting.summary
            })

        # Extract key votes/ordinances
        key_actions = []
        for meeting in meetings:
            for vote in (meeting.votes or []):
                if vote.get("result") in ["approved", "passed"]:
                    key_actions.append({
                        "jurisdiction": meeting.jurisdiction,
                        "date": meeting.meeting_date.isoformat() if meeting.meeting_date else None,
                        "item": vote.get("item"),
                        "result": vote.get("result")
                    })

        return {
            "total_meetings": len(meetings),
            "by_jurisdiction": dict(by_jurisdiction),
            "key_actions": key_actions[:10]
        }

    async def _summarize_zoning_activity(self, cutoff: datetime) -> Optional[Dict]:
        """Summarize zoning/planning activity."""
        # New cases
        new_query = select(ZoningCase).where(
            ZoningCase.filed_date >= cutoff.date()
        )
        new_result = await self.db.execute(new_query)
        new_cases = new_result.scalars().all()

        # Decided cases
        decided_query = select(ZoningCase).where(
            ZoningCase.decision_date >= cutoff.date()
        )
        decided_result = await self.db.execute(decided_query)
        decided_cases = decided_result.scalars().all()

        if not new_cases and not decided_cases:
            return None

        # Group by type
        by_type = defaultdict(int)
        for case in new_cases:
            by_type[case.case_type or "unknown"] += 1

        # Decision outcomes
        outcomes = defaultdict(int)
        for case in decided_cases:
            outcomes[case.status or "unknown"] += 1

        # Notable cases (large acreage or significant)
        notable = []
        for case in new_cases:
            if (case.acreage and case.acreage > 5) or case.case_type == "rezoning":
                notable.append({
                    "case_number": case.case_number,
                    "address": case.address,
                    "type": case.case_type,
                    "description": case.description[:200] if case.description else None,
                    "acreage": case.acreage
                })

        return {
            "new_cases": len(new_cases),
            "decided_cases": len(decided_cases),
            "by_type": dict(by_type),
            "outcomes": dict(outcomes),
            "notable_cases": notable[:5]
        }

    async def _summarize_permit_activity(self, cutoff: datetime) -> Optional[Dict]:
        """Summarize building permit activity."""
        query = select(BuildingPermit).where(
            BuildingPermit.applied_date >= cutoff.date()
        )
        result = await self.db.execute(query)
        permits = result.scalars().all()

        if not permits:
            return None

        # Group by type
        by_type = defaultdict(int)
        total_value = 0
        for permit in permits:
            by_type[permit.permit_type or "unknown"] += 1
            total_value += permit.estimated_value or 0

        # Group by jurisdiction
        by_jurisdiction = defaultdict(int)
        for permit in permits:
            by_jurisdiction[permit.jurisdiction] += 1

        # Significant projects
        significant = sorted(
            [p for p in permits if p.estimated_value and p.estimated_value > 100000],
            key=lambda x: x.estimated_value or 0,
            reverse=True
        )[:5]

        return {
            "total_permits": len(permits),
            "total_value": total_value,
            "by_type": dict(by_type),
            "by_jurisdiction": dict(by_jurisdiction),
            "significant_projects": [
                {
                    "permit_number": p.permit_number,
                    "address": p.address,
                    "type": p.permit_type,
                    "value": p.estimated_value,
                    "contractor": p.contractor
                }
                for p in significant
            ]
        }

    async def _summarize_property_activity(self, cutoff: datetime) -> Optional[Dict]:
        """Summarize property transaction activity."""
        query = select(PropertyTransaction).where(
            PropertyTransaction.sale_date >= cutoff.date()
        )
        result = await self.db.execute(query)
        transactions = result.scalars().all()

        if not transactions:
            return None

        # Statistics
        prices = [t.sale_price for t in transactions if t.sale_price and t.sale_price > 0]

        stats = {
            "total_transactions": len(transactions),
            "total_volume": sum(prices) if prices else 0,
            "avg_price": sum(prices) / len(prices) if prices else 0,
            "median_price": sorted(prices)[len(prices) // 2] if prices else 0,
            "max_price": max(prices) if prices else 0
        }

        # By transaction type
        by_type = defaultdict(int)
        for trans in transactions:
            by_type[trans.transaction_type or "sale"] += 1

        # Notable transactions
        notable = sorted(
            [t for t in transactions if t.sale_price and t.sale_price > 500000],
            key=lambda x: x.sale_price or 0,
            reverse=True
        )[:5]

        # Active buyers (multiple purchases)
        buyer_counts = defaultdict(int)
        for trans in transactions:
            if trans.grantee:
                buyer_counts[trans.grantee] += 1

        active_buyers = [
            {"name": name, "purchases": count}
            for name, count in sorted(buyer_counts.items(), key=lambda x: x[1], reverse=True)
            if count > 1
        ][:5]

        return {
            **stats,
            "by_type": dict(by_type),
            "notable_sales": [
                {
                    "address": t.address,
                    "price": t.sale_price,
                    "grantor": t.grantor,
                    "grantee": t.grantee,
                    "date": t.sale_date.isoformat() if t.sale_date else None
                }
                for t in notable
            ],
            "active_buyers": active_buyers
        }

    async def _summarize_court_activity(self, cutoff: datetime) -> Optional[Dict]:
        """Summarize local court activity."""
        # New filings
        new_query = select(LocalCourtCase).where(
            LocalCourtCase.filed_date >= cutoff.date()
        )
        new_result = await self.db.execute(new_query)
        new_cases = new_result.scalars().all()

        if not new_cases:
            return None

        # By case type
        by_type = defaultdict(int)
        for case in new_cases:
            by_type[case.case_type or "unknown"] += 1

        # By court
        by_court = defaultdict(int)
        for case in new_cases:
            by_court[case.court] += 1

        return {
            "new_filings": len(new_cases),
            "by_type": dict(by_type),
            "by_court": dict(by_court)
        }

    async def _generate_executive_summary(self, briefing: Dict) -> str:
        """Generate LLM executive summary of briefing."""
        if not self.ollama:
            return ""

        sections = briefing.get("sections", {})

        prompt = f"""Summarize this local government activity report in 2-3 paragraphs:

Council Activity: {sections.get('council', 'No activity')}
Zoning Activity: {sections.get('zoning', 'No activity')}
Permit Activity: {sections.get('permits', 'No activity')}
Property Transactions: {sections.get('property', 'No activity')}

Focus on:
- Key decisions and their implications
- Notable development trends
- Large transactions or projects
- Anything unusual or significant"""

        try:
            response = await self.ollama.generate(
                model="qwen2.5-coder:14b",
                prompt=prompt
            )
            return response.get("response", "")
        except Exception as e:
            logger.error(f"Failed to generate executive summary: {e}")
            return ""

    async def analyze_council_agenda(self, meeting_id: UUID) -> Dict:
        """
        Analyze a specific council meeting agenda.

        Args:
            meeting_id: Meeting ID to analyze

        Returns:
            Analysis results
        """
        result = await self.db.execute(
            select(CouncilMeeting).where(CouncilMeeting.id == meeting_id)
        )
        meeting = result.scalar_one_or_none()

        if not meeting or not meeting.agenda_text:
            return {"error": "Meeting or agenda not found"}

        if not self.ollama:
            return {"error": "LLM not available for analysis"}

        prompt = f"""Analyze this city council agenda and identify:
1. Items that could affect residential property owners
2. Zoning or development changes
3. Tax or fee changes
4. Infrastructure projects
5. Business-related decisions
6. Environmental or community impact items

Agenda:
{meeting.agenda_text[:6000]}

Return JSON:
{{
    "property_impact": ["item description"],
    "zoning_changes": ["change description"],
    "financial_impact": ["tax/fee description"],
    "infrastructure": ["project description"],
    "business": ["business item"],
    "environmental": ["environmental item"],
    "key_takeaways": ["takeaway 1", "takeaway 2"],
    "summary": "Brief overall summary"
}}"""

        try:
            response = await self.ollama.generate(
                model="qwen2.5-coder:14b",
                prompt=prompt,
                format="json"
            )
            return response.get("response", {})
        except Exception as e:
            logger.error(f"Agenda analysis failed: {e}")
            return {"error": str(e)}

    async def get_activity_stats(self, jurisdiction: Optional[str] = None) -> Dict:
        """
        Get activity statistics for dashboard.

        Args:
            jurisdiction: Optional filter by jurisdiction

        Returns:
            Statistics dictionary
        """
        stats = {
            "zoning_cases": 0,
            "permits": 0,
            "property_transactions": 0,
            "court_cases": 0,
            "council_meetings": 0
        }

        # Build filters
        # Use naive datetime for PostgreSQL TIMESTAMP WITHOUT TIME ZONE columns
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        last_30 = now - timedelta(days=30)

        # Count zoning cases
        zoning_q = select(func.count(ZoningCase.id)).where(
            ZoningCase.collected_at >= last_30
        )
        if jurisdiction:
            zoning_q = zoning_q.where(ZoningCase.jurisdiction == jurisdiction)
        result = await self.db.execute(zoning_q)
        stats["zoning_cases"] = result.scalar() or 0

        # Count permits
        permit_q = select(func.count(BuildingPermit.id)).where(
            BuildingPermit.collected_at >= last_30
        )
        if jurisdiction:
            permit_q = permit_q.where(BuildingPermit.jurisdiction == jurisdiction)
        result = await self.db.execute(permit_q)
        stats["permits"] = result.scalar() or 0

        # Count property transactions
        prop_q = select(func.count(PropertyTransaction.id)).where(
            PropertyTransaction.collected_at >= last_30
        )
        if jurisdiction:
            prop_q = prop_q.where(PropertyTransaction.jurisdiction == jurisdiction)
        result = await self.db.execute(prop_q)
        stats["property_transactions"] = result.scalar() or 0

        # Count court cases
        court_q = select(func.count(LocalCourtCase.id)).where(
            LocalCourtCase.collected_at >= last_30
        )
        result = await self.db.execute(court_q)
        stats["court_cases"] = result.scalar() or 0

        # Count meetings
        meeting_q = select(func.count(CouncilMeeting.id)).where(
            CouncilMeeting.collected_at >= last_30
        )
        if jurisdiction:
            meeting_q = meeting_q.where(CouncilMeeting.jurisdiction == jurisdiction)
        result = await self.db.execute(meeting_q)
        stats["council_meetings"] = result.scalar() or 0

        stats["total"] = sum(stats.values())

        return stats

    async def find_entity_mentions(self, entity_name: str) -> Dict:
        """
        Find mentions of an entity across local government records.

        Args:
            entity_name: Entity name to search for

        Returns:
            Dictionary with mentions by source type
        """
        name_lower = entity_name.lower()
        mentions = {
            "zoning_cases": [],
            "permits": [],
            "property": [],
            "court_cases": [],
            "council_meetings": []
        }

        # Search zoning cases
        zoning_result = await self.db.execute(
            select(ZoningCase).where(
                func.lower(ZoningCase.applicant).contains(name_lower) |
                func.lower(ZoningCase.owner).contains(name_lower)
            ).limit(20)
        )
        for case in zoning_result.scalars():
            mentions["zoning_cases"].append({
                "case_number": case.case_number,
                "address": case.address,
                "role": "applicant" if name_lower in (case.applicant or "").lower() else "owner"
            })

        # Search permits
        permit_result = await self.db.execute(
            select(BuildingPermit).where(
                func.lower(BuildingPermit.owner).contains(name_lower) |
                func.lower(BuildingPermit.contractor).contains(name_lower)
            ).limit(20)
        )
        for permit in permit_result.scalars():
            mentions["permits"].append({
                "permit_number": permit.permit_number,
                "address": permit.address,
                "role": "owner" if name_lower in (permit.owner or "").lower() else "contractor"
            })

        # Search property transactions
        prop_result = await self.db.execute(
            select(PropertyTransaction).where(
                func.lower(PropertyTransaction.grantor).contains(name_lower) |
                func.lower(PropertyTransaction.grantee).contains(name_lower)
            ).limit(20)
        )
        for trans in prop_result.scalars():
            mentions["property"].append({
                "address": trans.address,
                "sale_date": trans.sale_date.isoformat() if trans.sale_date else None,
                "role": "seller" if name_lower in (trans.grantor or "").lower() else "buyer"
            })

        mentions["total"] = sum(len(v) for v in mentions.values())
        return mentions
