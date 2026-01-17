"""
ICEWS (Integrated Crisis Early Warning System) collector for The Pulse.

Collects political event data from the ICEWS project:
- Diplomatic interactions
- Conflict indicators
- Cooperation events
- Early warning signals

Data Source: https://dataverse.harvard.edu/dataverse/icews
Originally developed by Lockheed Martin, now maintained at Harvard Dataverse.
Free for research use.

NOTE: ICEWS data is released in bulk format (tab-delimited).
This collector checks for new data releases and imports recent events.
"""
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class ICEWSCollector(BaseCollector):
    """
    ICEWS event data collector for political event analysis.

    Features:
    - Downloads ICEWS event data from Harvard Dataverse
    - Parses political events with actors and targets
    - Extracts CAMEO event codes
    - Conflict/cooperation intensity scores

    Data from Harvard Dataverse. Free for research.
    """

    # Harvard Dataverse API
    DATAVERSE_API = "https://dataverse.harvard.edu/api"
    ICEWS_DATAVERSE = "icews"
    INFO_URL = "https://dataverse.harvard.edu/dataverse/icews"

    # CAMEO event type top-level categories
    CAMEO_CATEGORIES = {
        "01": "Make public statement",
        "02": "Appeal",
        "03": "Express intent to cooperate",
        "04": "Consult",
        "05": "Engage in diplomatic cooperation",
        "06": "Engage in material cooperation",
        "07": "Provide aid",
        "08": "Yield",
        "09": "Investigate",
        "10": "Demand",
        "11": "Disapprove",
        "12": "Reject",
        "13": "Threaten",
        "14": "Protest",
        "15": "Exhibit military posture",
        "16": "Reduce relations",
        "17": "Coerce",
        "18": "Assault",
        "19": "Fight",
        "20": "Engage in unconventional mass violence",
    }

    def __init__(
        self,
        data_file: Optional[str] = None,
        days_back: int = 30,
        max_events: int = 100,
    ):
        """
        Initialize ICEWS collector.

        Args:
            data_file: Path to local ICEWS data file (if pre-downloaded)
            days_back: Only include events from last N days
            max_events: Maximum events to return per run
        """
        super().__init__()
        self.data_file = data_file
        self.days_back = days_back
        self.max_events = max_events

        self._logger.info(
            "ICEWS collector initialized. Data available from Harvard Dataverse: "
            "https://dataverse.harvard.edu/dataverse/icews"
        )

    @property
    def name(self) -> str:
        return "ICEWS"

    @property
    def source_type(self) -> str:
        return "icews"

    async def _check_dataverse(
        self,
        session: aiohttp.ClientSession,
    ) -> Optional[Dict[str, Any]]:
        """Check Harvard Dataverse for ICEWS data info."""
        # Search for ICEWS datasets
        url = f"{self.DATAVERSE_API}/search"
        params = {
            "q": "ICEWS",
            "type": "dataset",
            "subtree": self.ICEWS_DATAVERSE,
            "per_page": 5,
            "sort": "date",
            "order": "desc",
        }

        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {})

        except Exception as e:
            self._logger.debug(f"Dataverse API error: {e}")

        return None

    def _parse_event(self, row: Dict[str, str]) -> Optional[CollectedItem]:
        """Parse an ICEWS event row into CollectedItem."""
        try:
            event_id = row.get("Event ID", "") or row.get("event_id", "")
            if not event_id:
                return None

            # Parse date
            event_date = row.get("Event Date", "") or row.get("event_date", "")
            if event_date:
                try:
                    # ICEWS date format: YYYY-MM-DD
                    published = datetime.strptime(event_date, "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Get actors
            source_actor = row.get("Source Name", "") or row.get("source_name", "")
            source_country = row.get("Source Country", "") or row.get("source_country", "")
            target_actor = row.get("Target Name", "") or row.get("target_name", "")
            target_country = row.get("Target Country", "") or row.get("target_country", "")

            # Get event details
            event_text = row.get("Event Text", "") or row.get("event_text", "")
            cameo_code = row.get("CAMEO Code", "") or row.get("cameo_code", "")

            # Get intensity (Goldstein scale: -10 to +10)
            intensity = row.get("Intensity", "") or row.get("intensity", "")
            try:
                intensity = float(intensity) if intensity else 0.0
            except ValueError:
                intensity = 0.0

            # Determine event type from CAMEO code
            event_type = "Political Event"
            if cameo_code and len(cameo_code) >= 2:
                top_code = cameo_code[:2]
                event_type = self.CAMEO_CATEGORIES.get(top_code, event_type)

            # Get location
            latitude = row.get("Latitude", "") or row.get("latitude", "")
            longitude = row.get("Longitude", "") or row.get("longitude", "")

            # Build title
            if source_actor and target_actor:
                title = f"{source_actor} → {target_actor}: {event_type}"
            else:
                title = f"{event_type}: {source_country or 'Unknown'}"

            # Build summary
            summary = event_text if event_text else title
            if intensity:
                intensity_label = "cooperative" if intensity > 0 else "conflictual"
                summary += f" (Intensity: {intensity:.1f}, {intensity_label})"

            return CollectedItem(
                source="icews",
                source_name="ICEWS Early Warning",
                source_url=self.INFO_URL,
                category="geopolitics",
                title=self.clean_text(title)[:200],
                summary=self.truncate_text(summary, 500),
                url=self.INFO_URL,
                published=published,
                metadata={
                    "event_id": event_id,
                    "event_date": event_date,
                    "source_actor": source_actor,
                    "source_country": source_country,
                    "target_actor": target_actor,
                    "target_country": target_country,
                    "event_type": event_type,
                    "cameo_code": cameo_code,
                    "intensity": intensity,
                    "latitude": float(latitude) if latitude else None,
                    "longitude": float(longitude) if longitude else None,
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse ICEWS event: {e}")
            return None

    async def _load_local_data(self) -> List[CollectedItem]:
        """Load ICEWS data from local file."""
        items = []

        if not self.data_file:
            self._logger.info(
                "No ICEWS data file configured. Download from Harvard Dataverse."
            )
            return items

        try:
            import os
            import csv

            if not os.path.exists(self.data_file):
                self._logger.error(f"ICEWS data file not found: {self.data_file}")
                return items

            # Calculate cutoff date
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)

            # Try to detect delimiter (ICEWS uses tab-delimited)
            with open(self.data_file, 'r', encoding='utf-8', errors='ignore') as f:
                sample = f.read(2048)
                delimiter = '\t' if '\t' in sample else ','

            with open(self.data_file, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                count = 0

                for row in reader:
                    # Filter by date
                    event_date = row.get("Event Date", "") or row.get("event_date", "")
                    if event_date:
                        try:
                            date = datetime.strptime(event_date, "%Y-%m-%d").replace(
                                tzinfo=timezone.utc
                            )
                            if date < cutoff:
                                continue
                        except ValueError:
                            pass

                    item = self._parse_event(row)
                    if item:
                        items.append(item)
                        count += 1

                        if count >= self.max_events:
                            break

            self._logger.info(f"Loaded {len(items)} events from ICEWS file")

        except Exception as e:
            self._logger.error(f"Failed to load ICEWS data: {e}")

        return items

    async def collect(self) -> List[CollectedItem]:
        """Fetch political events from ICEWS."""
        self._logger.info(f"Collecting from ICEWS (last {self.days_back} days)")

        # Check Dataverse for data info
        async with aiohttp.ClientSession() as session:
            dataverse_info = await self._check_dataverse(session)
            if dataverse_info:
                items = dataverse_info.get("items", [])
                if items:
                    latest = items[0]
                    self._logger.info(
                        f"Latest ICEWS dataset: {latest.get('name', 'Unknown')}"
                    )

        # Load from local file if available
        items = await self._load_local_data()

        if not items:
            self._logger.info(
                "ICEWS collection returned no items. To use ICEWS:\n"
                "1. Visit https://dataverse.harvard.edu/dataverse/icews\n"
                "2. Download the event data files\n"
                "3. Configure collector with data_file='/path/to/icews.tab'"
            )

        return items
