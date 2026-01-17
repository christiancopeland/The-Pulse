"""
MISP (Malware Information Sharing Platform) collector for The Pulse.

Integrates with self-hosted MISP instance for threat intelligence:
- MISP events and attributes
- IOCs (Indicators of Compromise)
- STIX/TAXII compatible feeds
- Threat actor and campaign data

Requires self-hosted MISP instance.
Documentation: https://www.misp-project.org/documentation/
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


class MISPCollector(BaseCollector):
    """
    MISP instance collector for threat intelligence aggregation.

    Features:
    - Fetches events from MISP REST API
    - Extracts attributes and IOCs
    - Supports STIX export format
    - Galaxy and taxonomy tagging

    Requires self-hosted MISP instance and API key.
    """

    def __init__(
        self,
        misp_url: Optional[str] = None,
        api_key: Optional[str] = None,
        verify_ssl: bool = True,
        days_back: int = 7,
        max_events: int = 50,
    ):
        """
        Initialize MISP collector.

        Args:
            misp_url: URL of MISP instance (e.g., https://misp.local)
            api_key: MISP API key (from user profile)
            verify_ssl: Verify SSL certificates
            days_back: Fetch events modified in last N days
            max_events: Maximum events to fetch per run
        """
        super().__init__()
        self.misp_url = (misp_url or os.getenv("MISP_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("MISP_API_KEY")
        self.verify_ssl = verify_ssl if verify_ssl else os.getenv("MISP_VERIFY_SSL", "true").lower() == "true"
        self.days_back = days_back
        self.max_events = max_events

        if not self.misp_url or not self.api_key:
            self._logger.warning(
                "MISP_URL or MISP_API_KEY not set - collector will be disabled. "
                "Configure MISP instance and set environment variables."
            )

    @property
    def name(self) -> str:
        return "MISP"

    @property
    def source_type(self) -> str:
        return "misp"

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "Authorization": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _fetch_events(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch recent events from MISP."""
        events = []

        # Calculate date filter
        since = datetime.now(timezone.utc) - timedelta(days=self.days_back)
        timestamp = int(since.timestamp())

        url = f"{self.misp_url}/events/restSearch"
        payload = {
            "returnFormat": "json",
            "timestamp": timestamp,
            "limit": self.max_events,
            "published": True,
        }

        try:
            ssl_context = None if self.verify_ssl else False

            async with session.post(
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                ssl=ssl_context,
            ) as response:
                if response.status == 403:
                    self._logger.error("MISP API key invalid or insufficient permissions")
                    return []
                elif response.status != 200:
                    self._logger.warning(f"MISP returned status {response.status}")
                    text = await response.text()
                    self._logger.debug(f"Response: {text[:500]}")
                    return []

                data = await response.json()
                # MISP returns {"response": [{"Event": {...}}, ...]}
                response_data = data.get("response", [])
                for item in response_data:
                    event = item.get("Event", {})
                    if event:
                        events.append(event)

                self._logger.debug(f"MISP: received {len(events)} events")

        except aiohttp.ClientSSLError as e:
            self._logger.error(f"MISP SSL error: {e}. Set MISP_VERIFY_SSL=false for self-signed certs.")
        except asyncio.TimeoutError:
            self._logger.warning(f"MISP timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"MISP error: {type(e).__name__}: {e}")

        return events

    def _extract_iocs(self, attributes: List[Dict]) -> Dict[str, List[str]]:
        """Extract IOCs from MISP attributes."""
        iocs = {
            "ip-dst": [],
            "ip-src": [],
            "domain": [],
            "hostname": [],
            "url": [],
            "md5": [],
            "sha1": [],
            "sha256": [],
            "email-src": [],
            "filename": [],
        }

        for attr in attributes:
            attr_type = attr.get("type", "")
            value = attr.get("value", "")

            if not value:
                continue

            if attr_type in iocs:
                iocs[attr_type].append(value)

        # Remove empty lists
        return {k: v for k, v in iocs.items() if v}

    def _event_to_item(self, event: Dict[str, Any]) -> Optional[CollectedItem]:
        """Convert MISP event to CollectedItem."""
        try:
            event_id = event.get("id", "")
            uuid = event.get("uuid", "")
            info = event.get("info", "Untitled Event")

            # Parse dates
            date = event.get("date", "")
            timestamp = event.get("timestamp", "")

            if timestamp:
                try:
                    published = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                except (ValueError, TypeError):
                    published = datetime.now(timezone.utc)
            elif date:
                try:
                    published = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Get organization
            org = event.get("Orgc", {})
            org_name = org.get("name", "") if org else ""

            # Get tags
            tags = event.get("Tag", [])
            tag_names = [t.get("name", "") for t in tags if t.get("name")]

            # Get threat level
            threat_level_id = event.get("threat_level_id", "4")
            threat_levels = {"1": "High", "2": "Medium", "3": "Low", "4": "Undefined"}
            threat_level = threat_levels.get(str(threat_level_id), "Unknown")

            # Get attributes and extract IOCs
            attributes = event.get("Attribute", [])
            iocs = self._extract_iocs(attributes)
            ioc_count = sum(len(v) for v in iocs.values())

            # Get galaxies (threat actors, malware, etc.)
            galaxies = event.get("Galaxy", [])
            galaxy_names = []
            for galaxy in galaxies:
                clusters = galaxy.get("GalaxyCluster", [])
                for cluster in clusters:
                    galaxy_names.append(cluster.get("value", ""))

            # Build summary
            summary_parts = []
            if threat_level != "Undefined":
                summary_parts.append(f"Threat: {threat_level}")
            if ioc_count:
                summary_parts.append(f"{ioc_count} IOCs")
            if galaxy_names:
                summary_parts.append(f"Related: {', '.join(galaxy_names[:3])}")
            if tag_names:
                # Show relevant tags (skip internal MISP tags)
                visible_tags = [t for t in tag_names if not t.startswith("misp-galaxy")][:5]
                if visible_tags:
                    summary_parts.append(f"Tags: {', '.join(visible_tags)}")

            summary = " | ".join(summary_parts) if summary_parts else info[:500]

            # Build URL
            url = f"{self.misp_url}/events/view/{event_id}"

            return CollectedItem(
                source="misp",
                source_name=f"MISP ({org_name})" if org_name else "MISP",
                source_url=self.misp_url,
                category="cyber",
                title=self.clean_text(info),
                summary=self.truncate_text(summary, 500),
                url=url,
                published=published,
                author=org_name,
                metadata={
                    "event_id": event_id,
                    "uuid": uuid,
                    "threat_level": threat_level,
                    "analysis": event.get("analysis", ""),
                    "organization": org_name,
                    "tags": tag_names,
                    "galaxies": galaxy_names,
                    "ioc_count": ioc_count,
                    "iocs": iocs,
                    "attribute_count": len(attributes),
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse MISP event: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch threat events from MISP."""
        if not self.misp_url or not self.api_key:
            self._logger.warning("MISP collection skipped - not configured")
            return []

        self._logger.info(f"Collecting from MISP (last {self.days_back} days)")
        items = []

        async with aiohttp.ClientSession() as session:
            events = await self._fetch_events(session)

            for event in events:
                item = self._event_to_item(event)
                if item:
                    items.append(item)

        self._logger.info(f"MISP collection complete: {len(items)} events")
        return items
