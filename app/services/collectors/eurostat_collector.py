"""
Eurostat Crime Statistics collector for The Pulse.

Collects European crime statistics from Eurostat's SDMX API:
- Homicide rates by country
- Robbery statistics
- Burglary data
- Property crime trends

API Documentation: https://ec.europa.eu/eurostat/web/sdmx-infospace/welcome
No API key required.
"""
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class EurostatCrimeCollector(BaseCollector):
    """
    Eurostat crime statistics collector for EU crime data.

    Features:
    - Fetches crime statistics by EU country
    - Supports multiple offense types
    - Annual data with historical trends
    - No API key required

    API: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/
    """

    # Eurostat SDMX REST API
    API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1"

    # Dataset codes for crime statistics
    DATASETS = {
        "crim_off_cat": "Recorded offences by offence category",
        "crim_hom_soff": "Intentional homicide",
    }

    # Key EU countries to monitor
    EU_COUNTRIES = [
        "DE",  # Germany
        "FR",  # France
        "IT",  # Italy
        "ES",  # Spain
        "PL",  # Poland
        "NL",  # Netherlands
        "BE",  # Belgium
        "SE",  # Sweden
        "AT",  # Austria
        "EU27_2020",  # EU-27 total
    ]

    # Offense categories
    OFFENSE_CATEGORIES = {
        "ICCS0101": "Intentional homicide",
        "ICCS0201": "Assault",
        "ICCS0301": "Sexual violence",
        "ICCS0401": "Robbery",
        "ICCS0501": "Burglary",
        "ICCS0502": "Theft",
        "ICCS0601": "Fraud",
    }

    def __init__(
        self,
        countries: Optional[List[str]] = None,
        years_back: int = 3,
    ):
        """
        Initialize Eurostat crime collector.

        Args:
            countries: List of country codes (default: major EU countries)
            years_back: Number of years of data to fetch
        """
        super().__init__()
        self.countries = countries or self.EU_COUNTRIES
        self.years_back = years_back

        current_year = datetime.now().year
        # Eurostat data typically lags 1-2 years
        self.end_year = current_year - 1
        self.start_year = self.end_year - years_back + 1

    @property
    def name(self) -> str:
        return "Eurostat Crime"

    @property
    def source_type(self) -> str:
        return "eurostat"

    async def _fetch_crime_data(
        self,
        session: aiohttp.ClientSession,
        dataset: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch crime data from Eurostat SDMX API."""
        # Build SDMX query
        # Format: /data/{dataset}/{dimensions}
        geo_filter = "+".join(self.countries)

        url = f"{self.API_BASE}/data/{dataset}"
        params = {
            "format": "JSON",
            "geo": geo_filter,
            "startPeriod": str(self.start_year),
            "endPeriod": str(self.end_year),
        }

        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    self._logger.debug(f"Eurostat {dataset} returned {response.status}")
                    return None

                data = await response.json()
                return {"dataset": dataset, "data": data}

        except asyncio.TimeoutError:
            self._logger.debug(f"Eurostat {dataset} timed out")
        except Exception as e:
            self._logger.debug(f"Eurostat {dataset} error: {e}")

        return None

    def _parse_sdmx_data(self, result: Dict[str, Any]) -> List[CollectedItem]:
        """Parse SDMX JSON response into CollectedItems."""
        items = []
        dataset = result.get("dataset", "")
        data = result.get("data", {})

        try:
            # SDMX-JSON format parsing
            dimensions = data.get("dimension", {})
            observations = data.get("value", {})

            if not observations:
                return items

            # Get dimension indices
            geo_dim = dimensions.get("geo", {})
            time_dim = dimensions.get("time", {})
            iccs_dim = dimensions.get("iccs", {})

            geo_categories = geo_dim.get("category", {}).get("index", {})
            time_categories = time_dim.get("category", {}).get("index", {})
            iccs_categories = iccs_dim.get("category", {}).get("index", {}) if iccs_dim else {}

            # Reverse index mappings
            geo_labels = geo_dim.get("category", {}).get("label", {})
            iccs_labels = iccs_dim.get("category", {}).get("label", {}) if iccs_dim else {}

            # Process observations (simplified - get latest year per country)
            for obs_key, value in observations.items():
                try:
                    # Parse observation key (format depends on dataset structure)
                    parts = obs_key.split(":")

                    # Find country and year from dimensions
                    # This is simplified - actual SDMX parsing is more complex
                    country_code = ""
                    year = self.end_year
                    offense = "Crime"

                    for i, part in enumerate(parts):
                        if part in geo_categories:
                            country_code = part
                        elif part.isdigit() and len(part) == 4:
                            year = int(part)
                        elif part in self.OFFENSE_CATEGORIES:
                            offense = self.OFFENSE_CATEGORIES.get(part, part)

                    if not country_code:
                        continue

                    country_name = geo_labels.get(country_code, country_code)

                    # Create item for significant data points
                    if value and float(value) > 0:
                        title = f"EU Crime: {country_name} - {offense} ({year})"
                        summary = f"{int(float(value)):,} recorded offenses"

                        items.append(CollectedItem(
                            source="eurostat",
                            source_name="Eurostat Crime Statistics",
                            source_url=self.API_BASE,
                            category="crime_international",
                            title=title,
                            summary=summary,
                            url=f"https://ec.europa.eu/eurostat/databrowser/view/{dataset}/",
                            published=datetime(year, 12, 31, tzinfo=timezone.utc),
                            metadata={
                                "country": country_name,
                                "country_code": country_code,
                                "year": year,
                                "offense_type": offense,
                                "count": int(float(value)),
                                "dataset": dataset,
                            },
                        ))

                except Exception as e:
                    self._logger.debug(f"Failed to parse observation: {e}")
                    continue

        except Exception as e:
            self._logger.warning(f"Failed to parse Eurostat SDMX data: {e}")

        return items

    async def collect(self) -> List[CollectedItem]:
        """Fetch crime statistics from Eurostat."""
        self._logger.info(
            f"Collecting from Eurostat ({self.start_year}-{self.end_year}, "
            f"countries: {len(self.countries)})"
        )
        items = []

        async with aiohttp.ClientSession() as session:
            # Fetch each dataset
            tasks = [
                self._fetch_crime_data(session, dataset)
                for dataset in self.DATASETS.keys()
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self._logger.debug(f"Eurostat task failed: {result}")
                    continue
                if result:
                    parsed = self._parse_sdmx_data(result)
                    items.extend(parsed)

        self._logger.info(f"Eurostat collection complete: {len(items)} statistics")
        return items
