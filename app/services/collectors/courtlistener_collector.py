"""
CourtListener collector for The Pulse.

Collects federal court opinions and case information from CourtListener:
- Supreme Court opinions
- Circuit Court decisions
- District Court rulings
- PACER mirror data

API Documentation: https://www.courtlistener.com/api/rest-info/
No API key required for basic access (rate-limited to 5000/day).
"""
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class CourtListenerCollector(BaseCollector):
    """
    CourtListener API collector for legal intelligence.

    Features:
    - Fetches recent federal court opinions
    - Filters by court level (SCOTUS, Circuit, District)
    - Extracts case metadata, judges, citations
    - Free API access (5000 requests/day limit)

    API: https://www.courtlistener.com/api/rest/v3/
    """

    API_BASE = "https://www.courtlistener.com/api/rest/v3"

    # Court types to fetch (by precedential status)
    PRECEDENTIAL_STATUSES = [
        "Published",
        "Precedential",
    ]

    # Court shortcuts for filtering
    COURT_LEVELS = {
        "scotus": ["scotus"],  # Supreme Court
        "circuit": [
            "ca1", "ca2", "ca3", "ca4", "ca5", "ca6", "ca7", "ca8", "ca9",
            "ca10", "ca11", "cadc", "cafc"
        ],  # Circuit Courts
        "district": [],  # Too many to list, fetch all
    }

    def __init__(
        self,
        max_opinions: int = 50,
        days_back: int = 7,
        include_scotus: bool = True,
        include_circuit: bool = True,
        include_district: bool = False,  # District courts produce many opinions
    ):
        """
        Initialize CourtListener collector.

        Args:
            max_opinions: Maximum opinions to fetch per run
            days_back: Only fetch opinions from last N days
            include_scotus: Include Supreme Court opinions
            include_circuit: Include Circuit Court opinions
            include_district: Include District Court opinions (high volume)
        """
        super().__init__()
        self.max_opinions = max_opinions
        self.days_back = days_back
        self.include_scotus = include_scotus
        self.include_circuit = include_circuit
        self.include_district = include_district

    @property
    def name(self) -> str:
        return "CourtListener"

    @property
    def source_type(self) -> str:
        return "courtlistener"

    def _get_court_filter(self) -> List[str]:
        """Build list of court IDs to filter."""
        courts = []
        if self.include_scotus:
            courts.extend(self.COURT_LEVELS["scotus"])
        if self.include_circuit:
            courts.extend(self.COURT_LEVELS["circuit"])
        # District courts are fetched separately if enabled
        return courts

    async def _fetch_opinions(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch opinions from CourtListener API."""
        opinions = []

        # Calculate date filter
        since = datetime.now(timezone.utc) - timedelta(days=self.days_back)
        date_filter = since.strftime("%Y-%m-%d")

        url = f"{self.API_BASE}/opinions/"

        # Build query parameters
        params = {
            "date_filed__gte": date_filter,
            "order_by": "-date_filed",
            "page_size": min(self.max_opinions, 100),  # API max is 100
        }

        # Add court filter if not including district courts
        court_filter = self._get_court_filter()
        if court_filter:
            params["cluster__docket__court__in"] = ",".join(court_filter)

        try:
            self._logger.debug(f"Querying CourtListener for opinions (last {self.days_back} days)")

            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "ThePulse/1.0 (contact: research@pulse.local)",
                }
            ) as response:
                if response.status == 429:
                    self._logger.warning("CourtListener rate limit exceeded")
                    return []
                elif response.status != 200:
                    self._logger.warning(f"CourtListener returned status {response.status}")
                    text = await response.text()
                    self._logger.debug(f"Response: {text[:500]}")
                    return []

                data = await response.json()
                results = data.get("results", [])
                count = data.get("count", 0)

                self._logger.debug(
                    f"CourtListener: received {len(results)} of {count} total opinions"
                )

                opinions = results

        except asyncio.TimeoutError:
            self._logger.warning(f"CourtListener timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"CourtListener error: {type(e).__name__}: {e}")

        return opinions

    async def _fetch_cluster_details(
        self,
        session: aiohttp.ClientSession,
        cluster_url: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch cluster (case) details for an opinion."""
        try:
            async with session.get(
                cluster_url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Accept": "application/json",
                    "User-Agent": "ThePulse/1.0",
                }
            ) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            self._logger.debug(f"Failed to fetch cluster: {e}")
        return None

    def _opinion_to_item(
        self,
        opinion: Dict[str, Any],
        cluster: Optional[Dict[str, Any]] = None,
    ) -> Optional[CollectedItem]:
        """Convert CourtListener opinion to CollectedItem."""
        try:
            opinion_id = opinion.get("id", "")

            # Get case name from cluster or opinion
            case_name = opinion.get("case_name", "") or ""
            if cluster:
                case_name = cluster.get("case_name", case_name)

            if not case_name:
                case_name = f"Opinion #{opinion_id}"

            # Parse date
            date_filed = opinion.get("date_filed")
            if date_filed:
                try:
                    published = datetime.strptime(date_filed, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Get opinion text excerpt
            plain_text = opinion.get("plain_text", "") or ""
            html = opinion.get("html", "") or ""

            # Prefer plain text, fall back to cleaned HTML
            content = plain_text or self.clean_text(html)
            summary = self.truncate_text(content, 500) if content else case_name

            # Extract metadata
            author = opinion.get("author_str", "") or ""
            court = ""
            docket_number = ""
            citations = []

            if cluster:
                docket = cluster.get("docket")
                if isinstance(docket, str) and docket.startswith("http"):
                    # It's a URL, not the actual docket data
                    pass
                elif isinstance(docket, dict):
                    court = docket.get("court_id", "")
                    docket_number = docket.get("docket_number", "")

                citations = cluster.get("citations", [])
                if not author:
                    judges = cluster.get("judges", "")
                    author = judges if judges else author

            # Build URL
            absolute_url = opinion.get("absolute_url", "")
            if absolute_url:
                url = f"https://www.courtlistener.com{absolute_url}"
            else:
                url = f"https://www.courtlistener.com/opinion/{opinion_id}/"

            # Determine court level for display
            court_display = court.upper() if court else "Federal Court"
            if court == "scotus":
                court_display = "Supreme Court"
            elif court and court.startswith("ca"):
                circuit_num = court[2:]
                court_display = f"Circuit Court ({circuit_num})"

            return CollectedItem(
                source="courtlistener",
                source_name=f"CourtListener ({court_display})",
                source_url=self.API_BASE,
                category="legal",
                title=self.clean_text(case_name),
                summary=summary,
                url=url,
                published=published,
                author=author,
                raw_content=content[:10000] if content else "",
                metadata={
                    "opinion_id": opinion_id,
                    "court": court,
                    "court_display": court_display,
                    "docket_number": docket_number,
                    "judges": author,
                    "citations": citations[:5] if citations else [],
                    "precedential_status": opinion.get("precedential_status", ""),
                    "type": opinion.get("type", ""),
                    "date_filed": date_filed,
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse CourtListener opinion: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch court opinions from CourtListener."""
        self._logger.info(f"Collecting from CourtListener (last {self.days_back} days)")
        items = []

        async with aiohttp.ClientSession() as session:
            opinions = await self._fetch_opinions(session)

            # Process opinions (optionally fetch cluster details)
            for opinion in opinions:
                # For now, skip cluster fetch to avoid rate limits
                # cluster = await self._fetch_cluster_details(session, opinion.get("cluster", ""))
                item = self._opinion_to_item(opinion, cluster=None)
                if item:
                    items.append(item)

                # Small delay to be respectful
                await asyncio.sleep(0.1)

        self._logger.info(f"CourtListener collection complete: {len(items)} opinions")
        return items
