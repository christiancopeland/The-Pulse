"""
AlienVault OTX (Open Threat Exchange) collector for The Pulse.

Collects threat intelligence from the AlienVault OTX community:
- Threat pulses with IOCs (Indicators of Compromise)
- Malware hashes, IPs, domains, URLs
- Adversary and malware family tagging
- Community-sourced threat intelligence

API Documentation: https://otx.alienvault.com/api
Rate Limits: 1000 requests/hour (free tier)
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


class OTXCollector(BaseCollector):
    """
    AlienVault OTX collector for threat intelligence.

    Features:
    - Fetches subscribed pulses and recent pulses
    - Extracts IOCs: IPv4, domains, hostnames, file hashes, URLs
    - Categorizes by adversary and malware families
    - Community-sourced threat intelligence

    Requires free API key from https://otx.alienvault.com/api
    """

    API_BASE = "https://otx.alienvault.com/api/v1"

    # IOC types to extract
    IOC_TYPES = [
        "IPv4", "IPv6", "domain", "hostname",
        "URL", "FileHash-MD5", "FileHash-SHA1", "FileHash-SHA256",
        "email", "CVE", "YARA", "mutex"
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_pulses: int = 50,
        days_back: int = 7,
    ):
        """
        Initialize OTX collector.

        Args:
            api_key: OTX API key (free from https://otx.alienvault.com/api)
            max_pulses: Maximum pulses to fetch per run
            days_back: Only fetch pulses from last N days
        """
        super().__init__()
        self.api_key = api_key or os.getenv("OTX_API_KEY")
        self.max_pulses = max_pulses
        self.days_back = days_back

        if not self.api_key:
            self._logger.warning(
                "OTX_API_KEY not set - collector will be disabled. "
                "Get free key at https://otx.alienvault.com/api"
            )

    @property
    def name(self) -> str:
        return "AlienVault OTX"

    @property
    def source_type(self) -> str:
        return "otx"

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "X-OTX-API-KEY": self.api_key,
            "Accept": "application/json",
            "User-Agent": "ThePulse/1.0",
        }

    async def _fetch_subscribed_pulses(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch pulses from subscribed feeds."""
        pulses = []

        # Calculate modified_since for filtering
        since = datetime.now(timezone.utc) - timedelta(days=self.days_back)
        modified_since = since.strftime("%Y-%m-%dT%H:%M:%S")

        url = f"{self.API_BASE}/pulses/subscribed"
        params = {
            "limit": self.max_pulses,
            "modified_since": modified_since,
        }

        try:
            async with session.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 403:
                    self._logger.error("OTX API key invalid or expired")
                    return []
                elif response.status == 429:
                    self._logger.warning("OTX rate limit exceeded")
                    return []
                elif response.status != 200:
                    self._logger.warning(f"OTX subscribed returned {response.status}")
                    return []

                data = await response.json()
                pulses = data.get("results", [])
                self._logger.debug(f"OTX subscribed: received {len(pulses)} pulses")

        except asyncio.TimeoutError:
            self._logger.warning(f"OTX subscribed timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"OTX subscribed error: {type(e).__name__}: {e}")

        return pulses

    async def _fetch_recent_pulses(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch recently modified pulses (public)."""
        pulses = []

        url = f"{self.API_BASE}/pulses/activity"
        params = {"limit": self.max_pulses}

        try:
            async with session.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status != 200:
                    self._logger.warning(f"OTX activity returned {response.status}")
                    return []

                data = await response.json()
                pulses = data.get("results", [])
                self._logger.debug(f"OTX activity: received {len(pulses)} pulses")

        except asyncio.TimeoutError:
            self._logger.warning(f"OTX activity timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"OTX activity error: {type(e).__name__}: {e}")

        return pulses

    def _extract_iocs(self, indicators: List[Dict]) -> Dict[str, List[str]]:
        """Extract and categorize IOCs from pulse indicators."""
        iocs = {
            "ipv4": [],
            "ipv6": [],
            "domain": [],
            "hostname": [],
            "url": [],
            "file_hash_md5": [],
            "file_hash_sha1": [],
            "file_hash_sha256": [],
            "email": [],
            "cve": [],
        }

        for indicator in indicators:
            ioc_type = indicator.get("type", "")
            value = indicator.get("indicator", "")

            if not value:
                continue

            if ioc_type == "IPv4":
                iocs["ipv4"].append(value)
            elif ioc_type == "IPv6":
                iocs["ipv6"].append(value)
            elif ioc_type == "domain":
                iocs["domain"].append(value)
            elif ioc_type == "hostname":
                iocs["hostname"].append(value)
            elif ioc_type == "URL":
                iocs["url"].append(value)
            elif ioc_type == "FileHash-MD5":
                iocs["file_hash_md5"].append(value)
            elif ioc_type == "FileHash-SHA1":
                iocs["file_hash_sha1"].append(value)
            elif ioc_type == "FileHash-SHA256":
                iocs["file_hash_sha256"].append(value)
            elif ioc_type == "email":
                iocs["email"].append(value)
            elif ioc_type == "CVE":
                iocs["cve"].append(value)

        # Remove empty lists
        return {k: v for k, v in iocs.items() if v}

    def _pulse_to_item(self, pulse: Dict[str, Any]) -> Optional[CollectedItem]:
        """Convert OTX pulse to CollectedItem."""
        try:
            pulse_id = pulse.get("id", "")
            name = pulse.get("name", "Untitled Pulse")
            description = pulse.get("description", "")

            # Parse dates
            created = pulse.get("created")
            modified = pulse.get("modified")

            if modified:
                try:
                    published = datetime.fromisoformat(modified.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            elif created:
                try:
                    published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Extract metadata
            author = pulse.get("author", {}).get("username", "unknown")
            adversary = pulse.get("adversary", "")
            malware_families = pulse.get("malware_families", [])
            tags = pulse.get("tags", [])
            references = pulse.get("references", [])
            indicators = pulse.get("indicators", [])

            # Extract IOCs
            iocs = self._extract_iocs(indicators)
            ioc_count = sum(len(v) for v in iocs.values())

            # Build summary
            summary_parts = []
            if adversary:
                summary_parts.append(f"Adversary: {adversary}")
            if malware_families:
                summary_parts.append(f"Malware: {', '.join(malware_families[:3])}")
            if ioc_count:
                summary_parts.append(f"{ioc_count} IOCs")
            if tags:
                summary_parts.append(f"Tags: {', '.join(tags[:5])}")

            summary = " | ".join(summary_parts) if summary_parts else description[:500]

            # Truncate description for raw_content
            raw_content = self.clean_text(description)

            return CollectedItem(
                source="otx",
                source_name="AlienVault OTX",
                source_url=self.API_BASE,
                category="cyber",
                title=self.clean_text(name),
                summary=self.truncate_text(summary, 500),
                url=f"https://otx.alienvault.com/pulse/{pulse_id}",
                published=published,
                author=author,
                raw_content=raw_content,
                metadata={
                    "pulse_id": pulse_id,
                    "adversary": adversary,
                    "malware_families": malware_families,
                    "tags": tags,
                    "references": references[:10],  # Limit references
                    "ioc_count": ioc_count,
                    "iocs": iocs,
                    "targeted_countries": pulse.get("targeted_countries", []),
                    "industries": pulse.get("industries", []),
                    "attack_ids": pulse.get("attack_ids", []),  # MITRE ATT&CK
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse OTX pulse: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch threat pulses from OTX."""
        if not self.api_key:
            self._logger.warning("OTX collection skipped - no API key configured")
            return []

        self._logger.info(f"Collecting from OTX (last {self.days_back} days)")
        items = []
        seen_ids = set()

        async with aiohttp.ClientSession() as session:
            # Fetch both subscribed and recent pulses in parallel
            subscribed_task = self._fetch_subscribed_pulses(session)
            recent_task = self._fetch_recent_pulses(session)

            subscribed_pulses, recent_pulses = await asyncio.gather(
                subscribed_task, recent_task, return_exceptions=True
            )

            # Handle exceptions
            if isinstance(subscribed_pulses, Exception):
                self._logger.error(f"OTX subscribed failed: {subscribed_pulses}")
                subscribed_pulses = []
            if isinstance(recent_pulses, Exception):
                self._logger.error(f"OTX recent failed: {recent_pulses}")
                recent_pulses = []

            # Combine and deduplicate by pulse ID
            all_pulses = subscribed_pulses + recent_pulses

            for pulse in all_pulses:
                pulse_id = pulse.get("id")
                if pulse_id in seen_ids:
                    continue
                seen_ids.add(pulse_id)

                item = self._pulse_to_item(pulse)
                if item:
                    items.append(item)

        self._logger.info(f"OTX collection complete: {len(items)} pulses")
        return items
