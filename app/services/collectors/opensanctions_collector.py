"""
OpenSanctions Collector for The Pulse.

Collects sanctions data, PEP (Politically Exposed Persons) information,
and watchlist entries from the OpenSanctions API.

Coverage:
- International sanctions (OFAC, EU, UN, etc.)
- Politically Exposed Persons (PEPs)
- Watchlist entries
- Entity deduplication and matching
- Cross-referenced datasets

API Documentation: https://www.opensanctions.org/docs/api/
The basic API is FREE with rate limits. Higher limits available with API key.
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


# OpenSanctions dataset categories
DATASET_CATEGORIES = {
    "sanctions": "sanctions",
    "peps": "pep",
    "crime": "crime",
    "debarment": "sanctions",
    "poi": "watchlist",
    "default": "sanctions",
}


class OpenSanctionsCollector(BaseCollector):
    """
    Collector for OpenSanctions entity data.

    Features:
    - Real-time sanctions list updates
    - PEP (Politically Exposed Persons) monitoring
    - Entity screening capabilities
    - Cross-dataset matching
    - Relationship mapping

    The FREE tier provides:
    - Access to all datasets
    - Rate-limited API calls
    - Entity search and matching

    Optional API key provides higher rate limits.
    """

    API_BASE = "https://api.opensanctions.org"

    def __init__(
        self,
        api_key: Optional[str] = None,
        datasets: Optional[List[str]] = None,
        max_items: int = 100,
        days_back: int = 7,
    ):
        """
        Initialize OpenSanctions collector.

        Args:
            api_key: Optional API key for higher rate limits (set OPENSANCTIONS_API_KEY env var)
            datasets: List of datasets to query (default: ["default"])
                     Options: "default", "sanctions", "peps", "crime", etc.
            max_items: Maximum items to fetch per request
            days_back: Look back period for recent additions
        """
        super().__init__()
        self.api_key = api_key or os.getenv("OPENSANCTIONS_API_KEY", "")
        self.datasets = datasets or ["default"]
        self.max_items = max_items
        self.days_back = days_back

    @property
    def name(self) -> str:
        return "OpenSanctions"

    @property
    def source_type(self) -> str:
        return "opensanctions"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with optional auth."""
        headers = {
            "Accept": "application/json",
            "User-Agent": "ThePulse/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_category(self, entity: Dict[str, Any]) -> str:
        """Determine category from entity schema and datasets."""
        schema = entity.get("schema", "").lower()
        datasets = entity.get("datasets", [])

        # Check schema type
        if "person" in schema:
            # Check if PEP
            properties = entity.get("properties", {})
            if properties.get("position") or properties.get("political"):
                return "pep"

        # Check datasets
        for ds in datasets:
            ds_lower = ds.lower()
            if "sanction" in ds_lower or "ofac" in ds_lower:
                return "sanctions"
            if "pep" in ds_lower or "politically" in ds_lower:
                return "pep"
            if "crime" in ds_lower or "interpol" in ds_lower:
                return "crime"

        return "sanctions"

    def _build_title(self, entity: Dict[str, Any]) -> str:
        """Build a descriptive title for the entity."""
        caption = entity.get("caption", "Unknown Entity")
        schema = entity.get("schema", "Entity")
        datasets = entity.get("datasets", [])

        # Get primary dataset
        primary_dataset = datasets[0] if datasets else "Unknown Source"

        return f"{caption} ({schema}) - {primary_dataset}"

    def _build_summary(self, entity: Dict[str, Any]) -> str:
        """Build a summary from entity properties."""
        parts = []

        properties = entity.get("properties", {})

        # Add key properties
        if properties.get("description"):
            desc = properties["description"]
            if isinstance(desc, list):
                desc = desc[0]
            parts.append(desc)

        if properties.get("notes"):
            notes = properties["notes"]
            if isinstance(notes, list):
                notes = notes[0]
            parts.append(notes)

        if properties.get("reason"):
            reason = properties["reason"]
            if isinstance(reason, list):
                reason = reason[0]
            parts.append(f"Reason: {reason}")

        if properties.get("program"):
            program = properties["program"]
            if isinstance(program, list):
                program = ", ".join(program)
            parts.append(f"Program: {program}")

        # Add nationality/country
        if properties.get("country"):
            countries = properties["country"]
            if isinstance(countries, list):
                countries = ", ".join(countries[:3])
            parts.append(f"Country: {countries}")

        if not parts:
            parts.append(f"Entity listed in {len(entity.get('datasets', []))} dataset(s)")

        return " | ".join(parts)

    async def collect(self) -> List[CollectedItem]:
        """Fetch recent sanctions and entity updates from OpenSanctions."""
        items = []

        # Check if API key is available - the search endpoint requires authentication
        if not self.api_key:
            self._logger.warning(
                "OpenSanctions API key not configured. The /search endpoint requires authentication. "
                "Set OPENSANCTIONS_API_KEY environment variable, or consider using bulk data downloads "
                "from https://www.opensanctions.org/datasets/ for free access."
            )
            return items

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                # Query recent statements (entity changes)
                for dataset in self.datasets:
                    dataset_items = await self._fetch_dataset(session, dataset)
                    items.extend(dataset_items)

        except asyncio.TimeoutError:
            self._logger.warning(
                f"OpenSanctions API timed out after {API_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            self._logger.error(f"OpenSanctions collection error: {type(e).__name__}: {e}")

        self._logger.info(f"OpenSanctions collection complete: {len(items)} items")
        return items

    async def _fetch_dataset(
        self,
        session: aiohttp.ClientSession,
        dataset: str
    ) -> List[CollectedItem]:
        """Fetch entities from a specific dataset."""
        items = []

        try:
            # Use the catalog endpoint to get recent entities
            url = f"{self.API_BASE}/search/{dataset}"
            params = {
                "limit": str(self.max_items),
            }

            self._logger.debug(f"Querying OpenSanctions dataset: {dataset}")

            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 401:
                    self._logger.warning(
                        "OpenSanctions API authentication failed. Check your API key."
                    )
                    return items

                if response.status == 429:
                    self._logger.warning(
                        "OpenSanctions rate limit hit."
                    )
                    return items

                if response.status != 200:
                    self._logger.warning(
                        f"OpenSanctions {dataset} returned status {response.status}"
                    )
                    return items

                data = await response.json()
                entities = data.get("results", [])

                self._logger.debug(
                    f"OpenSanctions {dataset}: received {len(entities)} entities"
                )

                for entity in entities:
                    try:
                        # Parse dates
                        first_seen = entity.get("first_seen")
                        last_seen = entity.get("last_seen")

                        if first_seen:
                            try:
                                published = datetime.fromisoformat(
                                    first_seen.replace("Z", "+00:00")
                                )
                            except ValueError:
                                published = datetime.now(timezone.utc)
                        else:
                            published = datetime.now(timezone.utc)

                        # Build entity URL
                        entity_id = entity.get("id", "")
                        entity_url = f"https://opensanctions.org/entities/{entity_id}/"

                        # Get properties for metadata
                        properties = entity.get("properties", {})

                        items.append(CollectedItem(
                            source="opensanctions",
                            source_name="OpenSanctions",
                            source_url=url,
                            category=self._get_category(entity),
                            title=self.clean_text(self._build_title(entity)),
                            summary=self.truncate_text(self._build_summary(entity), 500),
                            url=entity_url,
                            published=published,
                            metadata={
                                "entity_id": entity_id,
                                "schema": entity.get("schema", ""),
                                "datasets": entity.get("datasets", []),
                                "referents": entity.get("referents", []),
                                "first_seen": first_seen,
                                "last_seen": last_seen,
                                "target": entity.get("target", False),
                                "caption": entity.get("caption", ""),
                                "properties": {
                                    "name": properties.get("name", []),
                                    "alias": properties.get("alias", []),
                                    "country": properties.get("country", []),
                                    "birthDate": properties.get("birthDate", []),
                                    "nationality": properties.get("nationality", []),
                                    "position": properties.get("position", []),
                                    "program": properties.get("program", []),
                                },
                            },
                            raw_content=str(entity),
                        ))

                    except Exception as e:
                        self._logger.debug(f"Failed to parse OpenSanctions entity: {e}")
                        continue

        except Exception as e:
            self._logger.warning(f"OpenSanctions {dataset} error: {type(e).__name__}: {e}")

        return items

    async def screen_entity(
        self,
        entity_name: str,
        schema: str = "Person"
    ) -> Optional[Dict[str, Any]]:
        """
        Screen an entity against sanctions lists.

        Args:
            entity_name: Name to search for
            schema: Entity type ("Person", "Company", "Organization")

        Returns:
            Dict with match results or None if error
        """
        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                url = f"{self.API_BASE}/match/default"
                params = {
                    "q": entity_name,
                    "schema": schema,
                    "limit": "5",
                }

                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])

                        if results:
                            return {
                                "matched": True,
                                "query": entity_name,
                                "matches": results,
                                "highest_score": results[0].get("score", 0),
                                "total_matches": len(results),
                            }
                        return {
                            "matched": False,
                            "query": entity_name,
                            "matches": [],
                        }

                    self._logger.warning(
                        f"OpenSanctions screening returned status {response.status}"
                    )

        except Exception as e:
            self._logger.error(f"OpenSanctions screening error: {e}")

        return None

    async def get_entity_details(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full details for a specific entity.

        Args:
            entity_id: OpenSanctions entity ID

        Returns:
            Full entity data or None if not found
        """
        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                url = f"{self.API_BASE}/entities/{entity_id}"

                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        return await response.json()

        except Exception as e:
            self._logger.error(f"Failed to get entity details: {e}")

        return None
