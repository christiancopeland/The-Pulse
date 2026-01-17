"""
Humanitarian Data Exchange (HDX) collector for The Pulse.

Collects humanitarian datasets from OCHA's HDX platform:
- Crisis-specific datasets
- Refugee and displacement data
- Food security assessments
- Population statistics

API Documentation: https://data.humdata.org/documentation
No API key required.
"""
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class HDXCollector(BaseCollector):
    """
    Humanitarian Data Exchange API collector.

    Features:
    - Fetches recently updated humanitarian datasets
    - Filters by crisis-relevant tags
    - Extracts organization and country metadata
    - No API key required

    API: https://data.humdata.org/api/3/
    """

    API_BASE = "https://data.humdata.org/api/3"

    # Tags for crisis-relevant datasets
    CRISIS_TAGS = [
        "crisis",
        "displacement",
        "refugees",
        "idps",
        "food-security",
        "conflict",
        "emergency",
        "humanitarian-needs",
        "protection",
        "health",
    ]

    def __init__(
        self,
        max_datasets: int = 50,
        days_back: int = 7,
    ):
        """
        Initialize HDX collector.

        Args:
            max_datasets: Maximum datasets to fetch per run
            days_back: Only fetch datasets updated in last N days
        """
        super().__init__()
        self.max_datasets = max_datasets
        self.days_back = days_back

    @property
    def name(self) -> str:
        return "HDX"

    @property
    def source_type(self) -> str:
        return "hdx"

    async def _fetch_recent_datasets(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch recently updated datasets from HDX."""
        datasets = []

        # HDX uses CKAN API
        url = f"{self.API_BASE}/action/package_search"

        # Calculate date filter
        since = datetime.now(timezone.utc) - timedelta(days=self.days_back)
        date_filter = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        params = {
            "rows": self.max_datasets,
            "sort": "metadata_modified desc",
            "fq": f"metadata_modified:[{date_filter} TO *]",
        }

        try:
            self._logger.debug(f"Querying HDX for datasets (last {self.days_back} days)")

            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                headers={"Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    self._logger.warning(f"HDX returned status {response.status}")
                    return []

                data = await response.json()
                if data.get("success"):
                    results = data.get("result", {})
                    datasets = results.get("results", [])
                    count = results.get("count", 0)
                    self._logger.debug(f"HDX: received {len(datasets)} of {count} datasets")

        except asyncio.TimeoutError:
            self._logger.warning(f"HDX timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"HDX error: {type(e).__name__}: {e}")

        return datasets

    def _dataset_to_item(self, dataset: Dict[str, Any]) -> Optional[CollectedItem]:
        """Convert HDX dataset to CollectedItem."""
        try:
            dataset_id = dataset.get("id", "")
            name = dataset.get("name", "")
            title = dataset.get("title", name)
            notes = dataset.get("notes", "")

            # Parse dates
            modified = dataset.get("metadata_modified")
            created = dataset.get("metadata_created")

            if modified:
                try:
                    published = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Extract metadata
            organization = dataset.get("organization", {})
            org_title = organization.get("title", "") if organization else ""

            # Get groups (countries)
            groups = dataset.get("groups", [])
            countries = [g.get("title", "") for g in groups if g.get("title")]

            # Get tags
            tags = dataset.get("tags", [])
            tag_names = [t.get("name", "") for t in tags if t.get("name")]

            # Get resources count
            resources = dataset.get("resources", [])
            resources_count = len(resources)

            # Get update frequency
            update_frequency = dataset.get("data_update_frequency", "")

            # Build summary
            summary_parts = []
            if countries:
                summary_parts.append(f"Countries: {', '.join(countries[:3])}")
            if org_title:
                summary_parts.append(f"By: {org_title}")
            if tag_names:
                summary_parts.append(f"Tags: {', '.join(tag_names[:5])}")
            if resources_count:
                summary_parts.append(f"{resources_count} resources")

            summary = " | ".join(summary_parts) if summary_parts else notes[:500]

            # Build URL
            url = f"https://data.humdata.org/dataset/{name}"

            return CollectedItem(
                source="hdx",
                source_name=f"HDX ({org_title})" if org_title else "HDX",
                source_url=self.API_BASE,
                category="humanitarian",
                title=self.clean_text(title),
                summary=self.truncate_text(summary, 500),
                url=url,
                published=published,
                author=org_title,
                raw_content=self.clean_text(notes)[:5000] if notes else "",
                metadata={
                    "dataset_id": dataset_id,
                    "dataset_name": name,
                    "organization": org_title,
                    "countries": countries,
                    "tags": tag_names,
                    "resources_count": resources_count,
                    "update_frequency": update_frequency,
                    "license": dataset.get("license_title", ""),
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse HDX dataset: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch humanitarian datasets from HDX."""
        self._logger.info(f"Collecting from HDX (last {self.days_back} days)")
        items = []

        async with aiohttp.ClientSession() as session:
            datasets = await self._fetch_recent_datasets(session)

            for dataset in datasets:
                item = self._dataset_to_item(dataset)
                if item:
                    items.append(item)

        self._logger.info(f"HDX collection complete: {len(items)} datasets")
        return items
