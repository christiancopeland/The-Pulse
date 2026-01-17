"""
FBI Crime Data Explorer collector for The Pulse.

Collects US crime statistics from the FBI's Crime Data Explorer API:
- National crime trends (UCR Summary/NIBRS)
- State-level crime statistics
- Offense type breakdowns
- Victim demographics

API Documentation: https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi
Requires free API key registration.
"""
import asyncio
import aiohttp
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class FBICrimeDataCollector(BaseCollector):
    """
    FBI Crime Data Explorer API collector for crime statistics.

    Features:
    - Fetches national and state-level crime trends
    - Supports UCR Summary and NIBRS data
    - Offense type breakdowns (violent, property, etc.)
    - Historical trend analysis

    Requires free API key from https://api.usa.gov/
    """

    API_BASE = "https://api.usa.gov/crime/fbi/cde"

    # Offense categories to fetch
    OFFENSE_CATEGORIES = [
        "violent-crime",
        "property-crime",
        "homicide",
        "robbery",
        "aggravated-assault",
        "burglary",
        "larceny",
        "motor-vehicle-theft",
        "arson",
    ]

    # Key states to monitor (can be configured)
    DEFAULT_STATES = [
        "GA",  # Georgia (user's region)
        "TN",  # Tennessee (user's region)
        "CA",  # California
        "TX",  # Texas
        "FL",  # Florida
        "NY",  # New York
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        states: Optional[List[str]] = None,
        years_back: int = 3,
    ):
        """
        Initialize FBI Crime Data collector.

        Args:
            api_key: FBI CDE API key (free from https://api.usa.gov/)
            states: List of state abbreviations to fetch (default: key states)
            years_back: Number of years of data to fetch
        """
        super().__init__()
        self.api_key = api_key or os.getenv("FBI_CDE_API_KEY")
        self.states = states or self.DEFAULT_STATES
        self.years_back = years_back

        # Calculate year range
        current_year = datetime.now().year
        # FBI data typically lags 1-2 years
        self.end_year = current_year - 1
        self.start_year = self.end_year - years_back + 1

        if not self.api_key:
            self._logger.warning(
                "FBI_CDE_API_KEY not set - collector will be disabled. "
                "Get free key at https://api.usa.gov/"
            )

    @property
    def name(self) -> str:
        return "FBI Crime Data"

    @property
    def source_type(self) -> str:
        return "fbi_crime"

    async def _fetch_national_estimates(
        self,
        session: aiohttp.ClientSession,
        offense: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch national crime estimates for an offense type."""
        url = f"{self.API_BASE}/estimate/national/{offense}"
        params = {
            "from": self.start_year,
            "to": self.end_year,
            "API_KEY": self.api_key,
        }

        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 401:
                    self._logger.error("FBI CDE API key invalid")
                    return None
                elif response.status == 429:
                    self._logger.warning("FBI CDE rate limit exceeded")
                    return None
                elif response.status != 200:
                    self._logger.debug(f"FBI CDE {offense} returned {response.status}")
                    return None

                data = await response.json()
                return {"offense": offense, "level": "national", "data": data}

        except asyncio.TimeoutError:
            self._logger.debug(f"FBI CDE {offense} timed out")
        except Exception as e:
            self._logger.debug(f"FBI CDE {offense} error: {e}")

        return None

    async def _fetch_state_estimates(
        self,
        session: aiohttp.ClientSession,
        state: str,
        offense: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch state-level crime estimates."""
        url = f"{self.API_BASE}/estimate/state/{state}/{offense}"
        params = {
            "from": self.start_year,
            "to": self.end_year,
            "API_KEY": self.api_key,
        }

        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                return {"offense": offense, "level": "state", "state": state, "data": data}

        except Exception:
            pass

        return None

    def _format_offense_name(self, offense: str) -> str:
        """Format offense slug to readable name."""
        return offense.replace("-", " ").title()

    def _estimate_to_item(self, estimate: Dict[str, Any]) -> Optional[CollectedItem]:
        """Convert FBI estimate data to CollectedItem."""
        try:
            offense = estimate.get("offense", "")
            level = estimate.get("level", "national")
            state = estimate.get("state", "")
            data = estimate.get("data", {})

            # Handle different response structures
            if isinstance(data, dict):
                results = data.get("results", []) or data.get("data", [])
            elif isinstance(data, list):
                results = data
            else:
                return None

            if not results:
                return None

            # Get most recent year's data
            latest = None
            for entry in results:
                if isinstance(entry, dict):
                    year = entry.get("year") or entry.get("data_year")
                    if year and (latest is None or year > latest.get("year", 0)):
                        latest = entry

            if not latest:
                return None

            # Extract statistics
            year = latest.get("year") or latest.get("data_year", self.end_year)
            count = latest.get("value") or latest.get("actual") or latest.get("count", 0)
            rate = latest.get("rate") or latest.get("rate_per_100k", 0)

            # Build title and summary
            offense_name = self._format_offense_name(offense)
            if level == "national":
                jurisdiction = "United States"
                title = f"National {offense_name} Statistics ({year})"
            else:
                jurisdiction = state
                title = f"{state} {offense_name} Statistics ({year})"

            # Format numbers
            count_str = f"{count:,}" if isinstance(count, (int, float)) else str(count)
            rate_str = f"{rate:.1f}" if isinstance(rate, (int, float)) else str(rate)

            summary = f"{offense_name}: {count_str} incidents"
            if rate:
                summary += f" ({rate_str} per 100,000)"

            # Create item
            return CollectedItem(
                source="fbi_crime",
                source_name="FBI Crime Data Explorer",
                source_url=self.API_BASE,
                category="crime_national",
                title=title,
                summary=summary,
                url="https://cde.ucr.cjis.gov/",
                published=datetime(year, 12, 31, tzinfo=timezone.utc),  # End of reported year
                metadata={
                    "year": year,
                    "jurisdiction": jurisdiction,
                    "jurisdiction_level": level,
                    "state": state if level == "state" else None,
                    "offense_type": offense,
                    "offense_name": offense_name,
                    "count": count,
                    "rate_per_100k": rate,
                    "data_source": "UCR",
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse FBI estimate: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch crime statistics from FBI CDE."""
        if not self.api_key:
            self._logger.warning("FBI CDE collection skipped - no API key configured")
            return []

        self._logger.info(
            f"Collecting from FBI CDE ({self.start_year}-{self.end_year}, "
            f"states: {self.states})"
        )
        items = []

        async with aiohttp.ClientSession() as session:
            # Fetch national estimates for key offenses
            national_tasks = [
                self._fetch_national_estimates(session, offense)
                for offense in self.OFFENSE_CATEGORIES[:5]  # Limit to top 5
            ]

            # Fetch state estimates for priority states
            state_tasks = []
            for state in self.states[:3]:  # Limit to top 3 states
                for offense in ["violent-crime", "property-crime"]:
                    state_tasks.append(
                        self._fetch_state_estimates(session, state, offense)
                    )

            # Run all fetches
            all_results = await asyncio.gather(
                *national_tasks, *state_tasks,
                return_exceptions=True
            )

            # Process results
            for result in all_results:
                if isinstance(result, Exception):
                    self._logger.debug(f"FBI CDE task failed: {result}")
                    continue
                if result:
                    item = self._estimate_to_item(result)
                    if item:
                        items.append(item)

        self._logger.info(f"FBI CDE collection complete: {len(items)} statistics")
        return items
