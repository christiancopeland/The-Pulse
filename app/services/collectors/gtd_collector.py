"""
Global Terrorism Database (GTD) collector for The Pulse.

Collects terrorism incident data from START (National Consortium for
the Study of Terrorism and Responses to Terrorism) at University of Maryland:
- Terrorism incidents worldwide since 1970
- Attack types, targets, perpetrators
- Casualty data
- Geographic coding

Data Source: https://www.start.umd.edu/gtd/
Free for academic/research use. Commercial use requires license.

NOTE: GTD data is released annually in bulk CSV format.
This collector checks for new data releases and imports recent incidents.
"""
import asyncio
import aiohttp
import csv
import io
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class GTDCollector(BaseCollector):
    """
    Global Terrorism Database collector for terrorism analysis.

    Features:
    - Downloads GTD incident data
    - Parses terrorism incidents with location and actor data
    - Categorizes by attack type and target
    - Extracts casualty information

    Data updated annually. Free for research use.
    """

    # GTD doesn't have a public API - data must be downloaded
    # This is a placeholder URL - actual data requires registration
    DATA_URL = "https://www.start.umd.edu/gtd/downloads"
    INFO_URL = "https://www.start.umd.edu/gtd/"

    # Attack type codes to names
    ATTACK_TYPES = {
        1: "Assassination",
        2: "Armed Assault",
        3: "Bombing/Explosion",
        4: "Hijacking",
        5: "Hostage Taking (Barricade)",
        6: "Hostage Taking (Kidnapping)",
        7: "Facility/Infrastructure Attack",
        8: "Unarmed Assault",
        9: "Unknown",
    }

    # Target type codes to names
    TARGET_TYPES = {
        1: "Business",
        2: "Government (General)",
        3: "Police",
        4: "Military",
        5: "Abortion Related",
        6: "Airports & Aircraft",
        7: "Government (Diplomatic)",
        8: "Educational Institution",
        9: "Food or Water Supply",
        10: "Journalists & Media",
        11: "Maritime",
        12: "NGO",
        13: "Other",
        14: "Private Citizens & Property",
        15: "Religious Figures/Institutions",
        16: "Telecommunication",
        17: "Terrorists/Non-State Militia",
        18: "Tourists",
        19: "Transportation",
        20: "Unknown",
        21: "Utilities",
        22: "Violent Political Party",
    }

    def __init__(
        self,
        data_file: Optional[str] = None,
        years: Optional[List[int]] = None,
        max_incidents: int = 100,
    ):
        """
        Initialize GTD collector.

        Args:
            data_file: Path to local GTD CSV file (if pre-downloaded)
            years: List of years to include (default: last 3 years)
            max_incidents: Maximum incidents to return per run
        """
        super().__init__()
        self.data_file = data_file
        self.max_incidents = max_incidents

        # Default to recent years
        current_year = datetime.now().year
        self.years = years or [current_year - 3, current_year - 2, current_year - 1]

        self._logger.info(
            "GTD collector initialized. Note: GTD data requires manual download "
            "from https://www.start.umd.edu/gtd/ (free registration required)"
        )

    @property
    def name(self) -> str:
        return "GTD"

    @property
    def source_type(self) -> str:
        return "gtd"

    def _parse_incident(self, row: Dict[str, str]) -> Optional[CollectedItem]:
        """Parse a GTD incident row into CollectedItem."""
        try:
            # Get event ID
            event_id = row.get("eventid", "")
            if not event_id:
                return None

            # Parse date
            year = int(row.get("iyear", 0))
            month = int(row.get("imonth", 0)) or 1
            day = int(row.get("iday", 0)) or 1

            # Validate date
            if year < 1970 or year > 2030:
                return None
            if month < 1 or month > 12:
                month = 1
            if day < 1 or day > 31:
                day = 1

            try:
                published = datetime(year, month, day, tzinfo=timezone.utc)
            except ValueError:
                published = datetime(year, 1, 1, tzinfo=timezone.utc)

            # Get location
            country = row.get("country_txt", "")
            region = row.get("region_txt", "")
            city = row.get("city", "")
            latitude = row.get("latitude", "")
            longitude = row.get("longitude", "")

            # Get attack details
            attack_type_code = int(row.get("attacktype1", 0) or 0)
            attack_type = self.ATTACK_TYPES.get(attack_type_code, "Unknown")

            target_type_code = int(row.get("targtype1", 0) or 0)
            target_type = self.TARGET_TYPES.get(target_type_code, "Unknown")
            target = row.get("target1", "")

            # Get perpetrator
            group_name = row.get("gname", "Unknown")

            # Get casualties
            killed = int(row.get("nkill", 0) or 0)
            wounded = int(row.get("nwound", 0) or 0)

            # Get weapon type
            weapon = row.get("weaptype1_txt", "")

            # Build summary
            summary = row.get("summary", "")
            if not summary:
                summary_parts = []
                if group_name and group_name != "Unknown":
                    summary_parts.append(f"By: {group_name}")
                summary_parts.append(f"Attack: {attack_type}")
                summary_parts.append(f"Target: {target_type}")
                if killed or wounded:
                    summary_parts.append(f"Casualties: {killed} killed, {wounded} wounded")
                summary = " | ".join(summary_parts)

            # Build title
            location = city if city else country
            title = f"{attack_type} in {location}, {country}"
            if group_name and group_name != "Unknown":
                title = f"{group_name}: {title}"

            return CollectedItem(
                source="gtd",
                source_name="Global Terrorism Database",
                source_url=self.INFO_URL,
                category="terrorism",
                title=self.clean_text(title)[:200],
                summary=self.truncate_text(summary, 500),
                url=f"https://www.start.umd.edu/gtd/search/IncidentSummary.aspx?gtdid={event_id}",
                published=published,
                metadata={
                    "event_id": event_id,
                    "year": year,
                    "month": month,
                    "day": day,
                    "country": country,
                    "region": region,
                    "city": city,
                    "latitude": float(latitude) if latitude else None,
                    "longitude": float(longitude) if longitude else None,
                    "attack_type": attack_type,
                    "attack_type_code": attack_type_code,
                    "target_type": target_type,
                    "target": target,
                    "group_name": group_name,
                    "weapon_type": weapon,
                    "killed": killed,
                    "wounded": wounded,
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse GTD incident: {e}")
            return None

    async def _load_local_data(self) -> List[CollectedItem]:
        """Load GTD data from local CSV file."""
        items = []

        if not self.data_file:
            self._logger.warning(
                "No GTD data file configured. Download from "
                "https://www.start.umd.edu/gtd/ and set data_file parameter."
            )
            return items

        try:
            import os
            if not os.path.exists(self.data_file):
                self._logger.error(f"GTD data file not found: {self.data_file}")
                return items

            with open(self.data_file, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                count = 0

                for row in reader:
                    # Filter by year
                    year = int(row.get("iyear", 0))
                    if year not in self.years:
                        continue

                    item = self._parse_incident(row)
                    if item:
                        items.append(item)
                        count += 1

                        if count >= self.max_incidents:
                            break

            self._logger.info(f"Loaded {len(items)} incidents from GTD file")

        except Exception as e:
            self._logger.error(f"Failed to load GTD data: {e}")

        return items

    async def collect(self) -> List[CollectedItem]:
        """Fetch terrorism incidents from GTD."""
        self._logger.info(f"Collecting from GTD (years: {self.years})")

        # GTD doesn't have a public API - load from local file if available
        items = await self._load_local_data()

        if not items:
            self._logger.info(
                "GTD collection returned no items. To use GTD:\n"
                "1. Register at https://www.start.umd.edu/gtd/\n"
                "2. Download the dataset CSV\n"
                "3. Configure collector with data_file='/path/to/gtd.csv'"
            )

        return items
