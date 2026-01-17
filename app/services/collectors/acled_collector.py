"""
ACLED (Armed Conflict Location & Event Data) Collector for The Pulse.

Collects armed conflict events, protests, riots, and political violence data
from the ACLED API. ACLED is FREE for research use with registration.

Coverage:
- Armed conflict events worldwide
- Protests and riots
- Violence against civilians
- Strategic developments
- Fatality tracking

API Documentation: https://apidocs.acleddata.com/
Registration (FREE): https://developer.acleddata.com/
"""
import asyncio
import aiohttp
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


# ACLED event type categories for intelligence prioritization
ACLED_EVENT_TYPES = {
    "Battles": "conflict",
    "Explosions/Remote violence": "conflict",
    "Violence against civilians": "conflict",
    "Protests": "political",
    "Riots": "political",
    "Strategic developments": "military",
}

# Severity scoring based on event characteristics
SEVERITY_WEIGHTS = {
    "Battles": 3,
    "Explosions/Remote violence": 3,
    "Violence against civilians": 3,
    "Protests": 1,
    "Riots": 2,
    "Strategic developments": 2,
}


class ACLEDCollector(BaseCollector):
    """
    Collector for ACLED conflict and protest data.

    Features:
    - Armed conflict event tracking
    - Protest and civil unrest monitoring
    - Fatality-based severity scoring
    - Actor identification (state, rebel, militia, etc.)
    - Geographic precision with coordinates

    Requirements:
    - Free ACLED API key (register at developer.acleddata.com)
    - Email address for API access

    All data is FREE for research and non-commercial use.
    """

    API_BASE = "https://api.acleddata.com/acled/read"

    def __init__(
        self,
        api_key: Optional[str] = None,
        email: Optional[str] = None,
        days_back: int = 7,
        max_items: int = 500,
        regions: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
    ):
        """
        Initialize ACLED collector.

        Args:
            api_key: ACLED API key (or set ACLED_API_KEY env var)
            email: Email for API access (or set ACLED_EMAIL env var)
            days_back: Number of days to look back for events
            max_items: Maximum items to fetch
            regions: Optional list of regions to filter (e.g., ["Middle East"])
            countries: Optional list of countries to filter (e.g., ["Ukraine", "Syria"])
        """
        super().__init__()
        self.api_key = api_key or os.getenv("ACLED_API_KEY", "")
        self.email = email or os.getenv("ACLED_EMAIL", "")
        self.days_back = days_back
        self.max_items = max_items
        self.regions = regions
        self.countries = countries

        if not self.api_key or not self.email:
            self._logger.warning(
                "ACLED credentials not configured. "
                "Set ACLED_API_KEY and ACLED_EMAIL environment variables. "
                "Register for FREE at https://developer.acleddata.com/"
            )

    @property
    def name(self) -> str:
        return "ACLED Conflict Data"

    @property
    def source_type(self) -> str:
        return "acled"

    def _calculate_severity(self, event: Dict[str, Any]) -> str:
        """
        Calculate severity level based on event characteristics.

        Factors:
        - Event type weight
        - Fatality count
        - Actor types involved

        Returns: "critical", "high", "medium", or "low"
        """
        score = 0

        # Event type weight
        event_type = event.get("event_type", "")
        score += SEVERITY_WEIGHTS.get(event_type, 1)

        # Fatality impact
        fatalities = int(event.get("fatalities", 0) or 0)
        if fatalities >= 100:
            score += 5
        elif fatalities >= 50:
            score += 4
        elif fatalities >= 10:
            score += 3
        elif fatalities >= 1:
            score += 2

        # Actor involvement (state actors increase severity)
        actor1 = event.get("actor1", "").lower()
        actor2 = event.get("actor2", "").lower()
        if any(term in actor1 or term in actor2 for term in ["military", "government", "police", "army"]):
            score += 1

        # Map score to severity
        if score >= 8:
            return "critical"
        elif score >= 5:
            return "high"
        elif score >= 3:
            return "medium"
        return "low"

    def _get_category(self, event: Dict[str, Any]) -> str:
        """Map ACLED event type to internal category."""
        event_type = event.get("event_type", "")
        return ACLED_EVENT_TYPES.get(event_type, "conflict")

    async def collect(self) -> List[CollectedItem]:
        """Fetch conflict events from ACLED API."""
        items = []

        if not self.api_key or not self.email:
            self._logger.error(
                "ACLED collection skipped: missing API credentials. "
                "Register for FREE at https://developer.acleddata.com/"
            )
            return items

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=self.days_back)

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "key": self.api_key,
                    "email": self.email,
                    "event_date": start_date.strftime("%Y-%m-%d"),
                    "event_date_where": ">=",
                    "limit": str(self.max_items),
                }

                # Optional filters
                if self.regions:
                    params["region"] = "|".join(self.regions)
                if self.countries:
                    params["country"] = "|".join(self.countries)

                self._logger.info(
                    f"Querying ACLED for events since {start_date.strftime('%Y-%m-%d')}"
                )

                async with session.get(
                    self.API_BASE,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        self._logger.error(
                            f"ACLED API returned status {response.status}"
                        )
                        return items

                    data = await response.json()

                    if not data.get("success", True):
                        error = data.get("error", "Unknown error")
                        self._logger.error(f"ACLED API error: {error}")
                        return items

                    events = data.get("data", [])
                    self._logger.info(f"ACLED returned {len(events)} events")

                    for event in events:
                        try:
                            # Parse event date
                            event_date_str = event.get("event_date", "")
                            try:
                                published = datetime.strptime(
                                    event_date_str, "%Y-%m-%d"
                                ).replace(tzinfo=timezone.utc)
                            except ValueError:
                                published = datetime.now(timezone.utc)

                            # Build title from event data
                            event_type = event.get("event_type", "Event")
                            sub_event = event.get("sub_event_type", "")
                            location = event.get("location", "Unknown location")
                            country = event.get("country", "")

                            title = f"{event_type}"
                            if sub_event:
                                title += f" ({sub_event})"
                            title += f" in {location}, {country}"

                            # Get fatalities for summary
                            fatalities = int(event.get("fatalities", 0) or 0)
                            notes = event.get("notes", "")

                            summary = notes[:500] if notes else ""
                            if fatalities > 0:
                                summary = f"[{fatalities} fatalities] {summary}"

                            # Calculate severity
                            severity = self._calculate_severity(event)
                            category = self._get_category(event)

                            # Build unique URL (ACLED doesn't provide direct URLs)
                            event_id = event.get("event_id_cnty", "")
                            url = f"https://acleddata.com/data-export-tool/?event_id={event_id}"

                            items.append(CollectedItem(
                                source="acled",
                                source_name="ACLED",
                                source_url=self.API_BASE,
                                category=category,
                                title=self.clean_text(title),
                                summary=self.truncate_text(summary, 500),
                                url=url,
                                published=published,
                                metadata={
                                    "event_id": event_id,
                                    "event_type": event_type,
                                    "sub_event_type": sub_event,
                                    "actor1": event.get("actor1", ""),
                                    "actor2": event.get("actor2", ""),
                                    "assoc_actor_1": event.get("assoc_actor_1", ""),
                                    "assoc_actor_2": event.get("assoc_actor_2", ""),
                                    "country": country,
                                    "admin1": event.get("admin1", ""),
                                    "admin2": event.get("admin2", ""),
                                    "admin3": event.get("admin3", ""),
                                    "location": location,
                                    "latitude": event.get("latitude"),
                                    "longitude": event.get("longitude"),
                                    "geo_precision": event.get("geo_precision"),
                                    "fatalities": fatalities,
                                    "severity": severity,
                                    "source": event.get("source", ""),
                                    "source_scale": event.get("source_scale", ""),
                                    "interaction": event.get("interaction", ""),
                                    "region": event.get("region", ""),
                                    "timestamp": event.get("timestamp", ""),
                                },
                                raw_content=notes,
                            ))

                        except Exception as e:
                            self._logger.debug(f"Failed to parse ACLED event: {e}")
                            continue

        except asyncio.TimeoutError:
            self._logger.warning(
                f"ACLED API timed out after {API_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            self._logger.error(f"ACLED collection error: {type(e).__name__}: {e}")

        self._logger.info(f"ACLED collection complete: {len(items)} items")
        return items

    async def get_event_counts_by_country(
        self,
        days_back: int = 30
    ) -> Dict[str, int]:
        """
        Get event counts by country for the specified period.

        Useful for trend analysis and hotspot detection.
        """
        counts: Dict[str, int] = {}

        if not self.api_key or not self.email:
            return counts

        start_date = datetime.now(timezone.utc) - timedelta(days=days_back)

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "key": self.api_key,
                    "email": self.email,
                    "event_date": start_date.strftime("%Y-%m-%d"),
                    "event_date_where": ">=",
                    "limit": "0",  # Just get counts
                }

                async with session.get(
                    self.API_BASE,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        for event in data.get("data", []):
                            country = event.get("country", "Unknown")
                            counts[country] = counts.get(country, 0) + 1

        except Exception as e:
            self._logger.error(f"Failed to get ACLED country counts: {e}")

        return counts
