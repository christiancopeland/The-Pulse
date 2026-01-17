"""
ReliefWeb API collector for The Pulse.

Collects humanitarian crisis reports from UN OCHA's ReliefWeb:
- Situation reports
- Flash updates
- Assessments
- Press releases
- Disaster updates

API Documentation: https://reliefweb.int/help/api
No API key required - free public API.
"""
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class ReliefWebCollector(BaseCollector):
    """
    ReliefWeb API collector for humanitarian intelligence.

    Features:
    - Fetches recent humanitarian reports and situation updates
    - Filters by report type, country, disaster
    - Extracts organization, themes, and geographic data
    - No API key required

    API: https://api.reliefweb.int/v1
    """

    API_BASE = "https://api.reliefweb.int/v1"

    # Report types to fetch (priority order)
    REPORT_TYPES = [
        "Situation Report",
        "Flash Update",
        "Assessment",
        "Press Release",
        "Map",
    ]

    def __init__(
        self,
        max_reports: int = 50,
        days_back: int = 3,
        report_types: Optional[List[str]] = None,
    ):
        """
        Initialize ReliefWeb collector.

        Args:
            max_reports: Maximum reports to fetch per run
            days_back: Only fetch reports from last N days
            report_types: List of report types to fetch (default: all priority types)
        """
        super().__init__()
        self.max_reports = max_reports
        self.days_back = days_back
        self.report_types = report_types or self.REPORT_TYPES

    @property
    def name(self) -> str:
        return "ReliefWeb"

    @property
    def source_type(self) -> str:
        return "reliefweb"

    async def _fetch_reports(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch reports from ReliefWeb API."""
        reports = []

        # Calculate date filter
        since = datetime.now(timezone.utc) - timedelta(days=self.days_back)
        date_filter = since.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        url = f"{self.API_BASE}/reports"

        # Build query payload
        payload = {
            "appname": "the-pulse",
            "limit": self.max_reports,
            "preset": "latest",
            "fields": {
                "include": [
                    "id", "title", "body", "url", "date.created", "date.original",
                    "source", "country", "disaster", "disaster_type", "theme",
                    "format", "language", "origin"
                ]
            },
            "filter": {
                "operator": "AND",
                "conditions": [
                    {
                        "field": "date.created",
                        "value": {"from": date_filter}
                    },
                    {
                        "field": "format.name",
                        "value": self.report_types,
                        "operator": "OR"
                    }
                ]
            },
            "sort": ["date.created:desc"]
        }

        try:
            self._logger.debug(f"Querying ReliefWeb for reports (last {self.days_back} days)")

            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                }
            ) as response:
                if response.status != 200:
                    self._logger.warning(f"ReliefWeb returned status {response.status}")
                    text = await response.text()
                    self._logger.debug(f"Response: {text[:500]}")
                    return []

                data = await response.json()
                reports = data.get("data", [])
                total = data.get("totalCount", 0)

                self._logger.debug(
                    f"ReliefWeb: received {len(reports)} of {total} total reports"
                )

        except asyncio.TimeoutError:
            self._logger.warning(f"ReliefWeb timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"ReliefWeb error: {type(e).__name__}: {e}")

        return reports

    def _report_to_item(self, report: Dict[str, Any]) -> Optional[CollectedItem]:
        """Convert ReliefWeb report to CollectedItem."""
        try:
            fields = report.get("fields", {})
            report_id = report.get("id", "")
            href = report.get("href", "")

            title = fields.get("title", "Untitled Report")
            body = fields.get("body", "")

            # Parse dates
            date_created = fields.get("date", {}).get("created")
            date_original = fields.get("date", {}).get("original")

            if date_created:
                try:
                    published = datetime.fromisoformat(date_created.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            elif date_original:
                try:
                    published = datetime.fromisoformat(date_original.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Extract metadata
            sources = fields.get("source", [])
            source_names = [s.get("name", "") for s in sources if s.get("name")]
            source_name = source_names[0] if source_names else "ReliefWeb"

            countries = fields.get("country", [])
            country_names = [c.get("name", "") for c in countries if c.get("name")]

            disasters = fields.get("disaster", [])
            disaster_names = [d.get("name", "") for d in disasters if d.get("name")]

            disaster_types = fields.get("disaster_type", [])
            disaster_type_names = [dt.get("name", "") for dt in disaster_types if dt.get("name")]

            themes = fields.get("theme", [])
            theme_names = [t.get("name", "") for t in themes if t.get("name")]

            report_format = fields.get("format", [])
            format_names = [f.get("name", "") for f in report_format if f.get("name")]
            report_type = format_names[0] if format_names else "Report"

            # Get URL
            url = fields.get("url", "") or href or f"https://reliefweb.int/node/{report_id}"

            # Build summary
            summary_parts = []
            if country_names:
                summary_parts.append(f"Countries: {', '.join(country_names[:3])}")
            if disaster_type_names:
                summary_parts.append(f"Type: {', '.join(disaster_type_names[:2])}")
            if disaster_names:
                summary_parts.append(f"Disaster: {disaster_names[0]}")

            # Use body excerpt if no structured summary
            if body:
                # Strip HTML and get first 300 chars
                body_text = self.clean_text(body)
                summary_parts.append(body_text[:300])

            summary = " | ".join(summary_parts[:3]) if summary_parts else title

            return CollectedItem(
                source="reliefweb",
                source_name=f"ReliefWeb ({source_name})",
                source_url=self.API_BASE,
                category="humanitarian",
                title=self.clean_text(title),
                summary=self.truncate_text(summary, 500),
                url=url,
                published=published,
                author=source_name,
                raw_content=self.clean_text(body)[:5000] if body else "",
                metadata={
                    "report_id": report_id,
                    "report_type": report_type,
                    "countries": country_names,
                    "disasters": disaster_names,
                    "disaster_types": disaster_type_names,
                    "themes": theme_names,
                    "sources": source_names,
                    "formats": format_names,
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse ReliefWeb report: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch humanitarian reports from ReliefWeb."""
        self._logger.info(f"Collecting from ReliefWeb (last {self.days_back} days)")
        items = []

        async with aiohttp.ClientSession() as session:
            reports = await self._fetch_reports(session)

            for report in reports:
                item = self._report_to_item(report)
                if item:
                    items.append(item)

        self._logger.info(f"ReliefWeb collection complete: {len(items)} reports")
        return items
